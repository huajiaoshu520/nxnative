// Execute a generated IGN buffer-image atomic fixture. First max(value, 1), then
// add its returned old value to texel zero; invalid first coordinates add zero.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <assert.h>

int main(int argc, const char **argv) { @autoreleasepool {
    assert(argc == 3);
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice(); assert(dev);
    NSError *error = nil;
    id<MTLLibrary> lib = [dev newLibraryWithURL:[NSURL fileURLWithPath:@(argv[1])] error:&error];
    assert(lib && !error);
    id<MTLFunction> fn = [lib newFunctionWithName:@"main0"]; assert(fn);
    id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:fn error:&error];
    assert(pso && !error);
    id<MTLBuffer> data = [dev newBufferWithLength:4096 options:MTLResourceStorageModeShared];
    uint32_t *words = data.contents;
    for (int i = 0; i < 1024; i++) words[i] = 3;
    MTLTextureDescriptor *desc = [MTLTextureDescriptor textureBufferDescriptorWithPixelFormat:MTLPixelFormatR32Uint
        width:8 resourceOptions:data.resourceOptions usage:MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite];
    id<MTLTexture> tex = [data newTextureWithDescriptor:desc offset:0 bytesPerRow:32]; assert(tex);
    id<MTLArgumentEncoder> args = [fn newArgumentEncoderWithBufferIndex:0];
    id<MTLBuffer> ab = [dev newBufferWithLength:args.encodedLength options:MTLResourceStorageModeShared];
    [args setArgumentBuffer:ab offset:0];
    [args setTexture:tex atIndex:0];
    [args setBuffer:data offset:0 atIndex:1];
    id<MTLCommandQueue> queue = [dev newCommandQueue];
    id<MTLCommandBuffer> command = [queue commandBuffer];
    id<MTLComputeCommandEncoder> enc = [command computeCommandEncoder];
    [enc setComputePipelineState:pso];
    [enc setBuffer:ab offset:0 atIndex:0];
    [enc useResource:data usage:MTLResourceUsageRead | MTLResourceUsageWrite];
    [enc useResource:tex usage:MTLResourceUsageRead | MTLResourceUsageWrite];
    [enc dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
    [enc endEncoding]; [command commit]; [command waitUntilCompleted];
    assert(command.status == MTLCommandBufferStatusCompleted);
    assert(words[0] == (uint32_t)atoi(argv[2]));
    for (int i = 1; i < 1024; i++) assert(words[i] == 3);
    puts("returning IGN atomic: result and sentinel checks passed");
    return 0;
}}
