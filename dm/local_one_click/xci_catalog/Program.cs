// Inspect actual CNMT metadata and expose an integrated XCI as separate NSPs.
// NCAs are copied unchanged; the upstream extractor still verifies and layers them.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using LibHac.Common;
using LibHac.Common.Keys;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Spl;
using LibHac.Tools.Fs;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;
using Path = System.IO.Path;

record Entry(string Name, long Size);
record Title(string TitleId, uint Version, string Type, string Meta, string[] Files);
static class P {
    static IFileSystem fs;
    static Dictionary<string,Entry> entries;
    static byte[] Read(string name) {
        var entry=entries[name];
        if(entry.Size>16*1024*1024) throw new Exception("Unexpected large metadata/ticket");
        using var f=new UniqueRef<IFile>();
        fs.OpenFile(ref f.Ref,("/"+name).ToU8Span(),OpenMode.Read).ThrowIfFailure();
        byte[] data=new byte[(int)entry.Size]; f.Get.Read(out long got,0,data,ReadOption.None).ThrowIfFailure();
        if(got!=data.Length) throw new Exception("Incomplete metadata/ticket");
        return data;
    }
    static Nca Open(KeySet keys,string name) {
        var f=new UniqueRef<IFile>(); fs.OpenFile(ref f.Ref,("/"+name).ToU8Span(),OpenMode.Read).ThrowIfFailure();
        return new Nca(keys,f.Release().AsStorage());
    }
    static int Main(string[] args) {
        try { Run(args); return 0; }
        catch(Exception e) { Console.Error.WriteLine("XCI metadata/export failed: "+e.Message);return 1; }
    }
    static void Run(string[] args) {
        if(args.Length!=2 && args.Length!=3) throw new Exception("usage: xci_catalog <prod.keys> <input.xci> [output folder]");
        var keys=ExternalKeyReader.ReadKeyFile(args[0]);
        var storage=new LocalStorage(args[1],FileAccess.Read);
        var xci=new Xci(keys,storage);
        if(!xci.HasPartition(XciPartitionType.Secure)) throw new Exception("XCI has no secure partition");
        fs=xci.OpenPartition(XciPartitionType.Secure);
        entries=fs.EnumerateEntries("*",SearchOptions.Default).Where(e=>e.Type==DirectoryEntryType.File)
            .ToDictionary(e=>e.Name,e=>new Entry(e.Name,e.Size),StringComparer.OrdinalIgnoreCase);
        foreach(var entry in entries.Values.Where(e=>e.Name.EndsWith(".tik",StringComparison.OrdinalIgnoreCase))) {
            var t=Read(entry.Name);
            if(t.Length<0x2b0 || t[0x281]!=0) throw new Exception("Unsupported personalized or truncated ticket");
            keys.ExternalKeySet.Add(new RightsId(t.AsSpan(0x2a0,0x10)),new AccessKey(t.AsSpan(0x180,0x10))).ThrowIfFailure();
        }
        var titles=new List<Title>();
        foreach(var entry in entries.Values.Where(e=>e.Name.EndsWith(".nca",StringComparison.OrdinalIgnoreCase))) {
            var nca=Open(keys,entry.Name);
            if(nca.Header.ContentType!=NcaContentType.Meta) continue;
            var meta=nca.OpenFileSystem(NcaSectionType.Data,IntegrityCheckLevel.ErrorOnInvalid);
            foreach(var cnmt in meta.EnumerateEntries("*.cnmt",SearchOptions.RecurseSubdirectories)) {
                using var f=new UniqueRef<IFile>();meta.OpenFile(ref f.Ref,cnmt.FullPath.ToU8Span(),OpenMode.Read).ThrowIfFailure();
                if(cnmt.Size<0x20 || cnmt.Size>16*1024*1024) throw new Exception("Invalid CNMT size");
                byte[] data=new byte[(int)cnmt.Size];f.Get.Read(out long got,0,data,ReadOption.None).ThrowIfFailure();
                if(got!=data.Length) throw new Exception("Truncated CNMT");
                ulong id=BitConverter.ToUInt64(data,0);uint version=BitConverter.ToUInt32(data,8);byte type=data[12];
                string kind=type switch { 0x80=>"application",0x81=>"patch",0x82=>"dlc",_=>throw new Exception($"Unsupported CNMT type {type:x2}") };
                int start=0x20+BitConverter.ToUInt16(data,14),count=BitConverter.ToUInt16(data,16);
                if(start>data.Length || count>(data.Length-start)/0x38) throw new Exception("Invalid CNMT content table");
                var files=new List<string>{entry.Name};
                for(int i=0;i<count;i++) {
                    int at=start+i*0x38;string name=Convert.ToHexString(data,at+0x20,16).ToLowerInvariant()+".nca";
                    // Delta fragments are not needed for full base+patch extraction.
                    if(data[at+0x36]==6) continue;
                    if(!entries.TryGetValue(name,out var content)) throw new Exception("Missing referenced content: "+name);
                    ulong size=0;for(int k=0;k<6;k++) size|=(ulong)data[at+0x30+k]<<(8*k);
                    if((ulong)content.Size!=size) throw new Exception("Content size mismatch: "+name);
                    files.Add(content.Name);
                }
                files.AddRange(entries.Keys.Where(n=>n.EndsWith(".tik",StringComparison.OrdinalIgnoreCase)||n.EndsWith(".cert",StringComparison.OrdinalIgnoreCase)));
                titles.Add(new Title(id.ToString("X16"),version,kind,entry.Name,files.Distinct(StringComparer.OrdinalIgnoreCase).ToArray()));
            }
        }
        if(titles.Count==0) throw new Exception("No readable application metadata in XCI");
        if(titles.GroupBy(t=>(t.TitleId,t.Version)).Any(g=>g.Count()>1)) throw new Exception("Duplicate title/version metadata");
        var bases=titles.Where(t=>t.Type=="application").ToArray();
        if(bases.Length!=1) throw new Exception("Expected exactly one base application in XCI");
        ulong app=Convert.ToUInt64(bases[0].TitleId,16);
        foreach(var t in titles) {
            ulong id=Convert.ToUInt64(t.TitleId,16);
            if(t.Type=="patch" && id!=(app|0x800UL)) throw new Exception("Patch belongs to another application");
            if(t.Type=="dlc" && ((id&~0xfffUL)-0x1000UL)!=app) throw new Exception("DLC belongs to another application");
        }
        if(args.Length==3) {
            Directory.CreateDirectory(args[2]);
            foreach(var title in titles) Export(title,Path.Combine(args[2],$"[{title.TitleId}][v{title.Version}].nsp"));
        }
        Console.WriteLine(JsonSerializer.Serialize(titles));
    }
    static void Export(Title title,string output) {
        if(File.Exists(output)) throw new Exception("Output already exists");
        var names=title.Files;var table=new MemoryStream();var offsets=new List<int>();
        foreach(string name in names) { offsets.Add((int)table.Length);table.Write(Encoding.UTF8.GetBytes(name));table.WriteByte(0); }
        long raw=0x10+names.Length*0x18+table.Length;
        while((0x10+names.Length*0x18+table.Length)%0x10!=0) table.WriteByte(0);
        using var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write);
        using var writer=new BinaryWriter(stream,Encoding.UTF8,true);
        writer.Write(Encoding.ASCII.GetBytes("PFS0"));writer.Write(names.Length);writer.Write((int)table.Length);writer.Write(0);
        long offset=0;
        for(int i=0;i<names.Length;i++) { writer.Write(offset);writer.Write(entries[names[i]].Size);writer.Write(offsets[i]);writer.Write(0);offset+=entries[names[i]].Size; }
        stream.Write(table.ToArray());byte[] buffer=new byte[8*1024*1024];
        foreach(string name in names) {
            using var f=new UniqueRef<IFile>();fs.OpenFile(ref f.Ref,("/"+name).ToU8Span(),OpenMode.Read).ThrowIfFailure();
            long size=entries[name].Size;
            for(long at=0;at<size;) {
                int count=(int)Math.Min(buffer.Length,size-at);f.Get.Read(out long got,at,buffer.AsSpan(0,count),ReadOption.None).ThrowIfFailure();
                if(got<=0) throw new Exception("Unexpected end of XCI content");stream.Write(buffer,0,(int)got);at+=got;
            }
        }
    }
}
