// Exercise alpha state through recorded replay and real Metal fragment execution.
// From dm/gfx/tests: python3 ../tools/test_dmsh_alpha.py --fixture /tmp/alpha-plain.metal /tmp/alpha-args.metal /tmp/alpha-fetch.metal
// make GAME=01006F8002326000 t_alpha && ./t_alpha /tmp/alpha-plain.metal /tmp/alpha-args.metal /tmp/alpha-fetch.metal
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t g_mod[MAX_MOD]; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c) do {checks++;if(!(c)){failed++;fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c);}}while(0)
static int accepts(int f,float a,float r) {
 switch(f){case 1:return 0;case 2:return a<r;case 3:return a==r;case 4:return a<=r;case 5:return a>r;case 6:return a!=r;case 7:return a>=r;default:return 1;}
}
static void run(const char *path,int mode) {
 NSError *error=nil; NSString *source=[NSString stringWithContentsOfFile:@(path) encoding:NSUTF8StringEncoding error:&error];
 id<MTLLibrary> lib=[g_dev newLibraryWithSource:source options:nil error:&error];
 if(!lib){fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);abort();}
 NvProg *pr=[NvProg new];
 pr->sh[0]=[NvShader new];pr->sh[0]->fn=[lib newFunctionWithName:@"vertex_main"];pr->sh[0]->stage=0;
 NvShader *ps=[NvShader new];pr->sh[1]=ps;if(mode==2){
  MTLFunctionConstantValues *fc=[MTLFunctionConstantValues new];
  for(int k=0;k<8;k++){BOOL off=NO,on=k==0;[fc setConstantValue:&off type:MTLDataTypeBool atIndex:32+k];[fc setConstantValue:&on type:MTLDataTypeBool atIndex:64+k];}
  ps->fn=[lib newFunctionWithName:@"main0" constantValues:fc error:&error];
  if(!ps->fn){fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);abort();}
 }else ps->fn=[lib newFunctionWithName:@"main0"];ps->stage=1;ps->rf.may_discard=1;
 if(mode==1){ps->ae=[ps->fn newArgumentEncoderWithBufferIndex:0];ps->arg_len=ps->ae.encodedLength;ps->rf.nb=1;ps->rf.b[0]=(nvn_rbind){.kind=NVN_RB_CBUF,.reg=0,.aid=0};}
 static prog_t program[3];program[mode].serial=98000+mode;serial_put(program[mode].serial,pr);
 static NSMutableArray *keep;if(!keep)keep=[NSMutableArray array];[keep addObject:pr];
 tex_t target={.magic=MAGIC('T','E','X',0),.serial=98100+mode};target.d=(nvn_texdesc){.width=8,.height=48,.depth=1,.samples=1,.levels=1,.target=NVN_TEXTURE_TARGET_2D,.format=NVN_FORMAT_RGBA8};
 uint8_t *commands;if(posix_memalign((void**)&commands,getpagesize(),65536))abort();memset(commands,0,65536);mtl_pool_add(commands,65536);
 *(float*)(commands+60000)=8;
 size_t used=0;
 #define EMIT(OP,X) do {size_t z=(8+sizeof(X)+7)&~7ull;op_hdr h={OP,(uint32_t)z};memcpy(commands+used,&h,8);memcpy(commands+used+8,&(X),sizeof(X));used+=z;}while(0)
 p_set_rt rt={.n=1};rt.color[0]=&target;EMIT(OP_SET_RT,rt);
 p_viewports vp={.n=1};vp.v[0][2]=8;vp.v[0][3]=48;EMIT(OP_VIEWPORTS,vp);
 p_clear_color cl={.index=0,.mask=15,.rgba={0,0,1,1}};EMIT(OP_CLEAR_COLOR,cl);
 p_bind_program bp={&program[mode],3};EMIT(OP_BIND_PROGRAM,bp);
 p_bind_buf ub={.stage=1,.index=0,.addr=(uint64_t)(commands+60000),.size=4};if(mode==1){EMIT(OP_BIND_UBO,ub);}
 float refs[]={0,.3125f,.5f,1,NAN,.5f};int row=0;
 for(int f=1;f<=8;f++)for(int j=0;j<6;j++,row++){
  p_bind_state bs={.kind=1};color_st cs={0,NVN_LOGIC_OP_COPY,(uint32_t)f};memcpy(bs.bytes,&cs,sizeof cs);EMIT(OP_BIND_STATE,bs);
  p_alpha_ref ar={refs[j]};EMIT(OP_ALPHA_REF,ar);
  p_scissor sc={0,row,8,1};EMIT(OP_SCISSOR,sc);
  p_draw dr={.prim=4,.count=3,.instances=1};EMIT(OP_DRAW,dr);
 }
 op_hdr end={OP_END,8};memcpy(commands+used,&end,8);
 #undef EMIT
 state_reset();CHECK(S.color.alpha_func==NVN_ALPHA_FUNC_ALWAYS);CHECK(S.alpha_ref==0);
 memset(&R,0,sizeof R);mtl_sub_begin();uint64_t handle=(uint64_t)commands;mtl_sub_index(&handle,1);mtl_exec(commands);
 id<MTLBuffer> pixels=[g_dev newBufferWithLength:256*48 options:MTLResourceStorageModeShared];
 [blit() copyFromTexture:tex_mtl(&target) sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(8,48,1) toBuffer:pixels destinationOffset:0 destinationBytesPerRow:256 destinationBytesPerImage:256*48];
 CHECK(mtl_wait(mtl_sub_commit(),5000000000ull));CHECK(!mtl_last_commit_error());
 row=0;uint8_t *px=pixels.contents;
 for(int f=1;f<=8;f++)for(int j=0;j<6;j++,row++)for(int x=0;x<8;x++){
  int want=accepts(f,(x+.5f)/8,refs[j]);
  if((px[row*256+x*4]>200)!=want)fprintf(stderr,"mode %d function %d ref %g x %d got %u\n",mode,f,refs[j],x,px[row*256+x*4]);
  CHECK((px[row*256+x*4]>200)==want);
 }
 if(mode==1)CHECK(g_stat_args_reuse>0);
 mtl_pool_del(commands);mtl_drain();free(commands);
}
int main(int argc,char **argv){@autoreleasepool{if(argc!=4)return 2;mtl_init();run(argv[1],0);run(argv[2],1);run(argv[3],2);printf("alpha replay: %d checks, %d failed\n",checks,failed);return failed!=0;}}
