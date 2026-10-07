/* Read-only macOS hardware snapshot. No root, listener, fan control or writes.
 * AppleSMC structures/key mapping adapted from macmon v0.8.2 (MIT).
 * Copyright (c) 2024 vladkens. See macmon-LICENSE.txt alongside this file.
 */
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#include <mach/mach.h>
#include <sys/sysctl.h>
#include <unistd.h>
#include <math.h>

typedef struct { uint8_t major,minor,build,reserved; uint16_t release; } SMCVersion;
typedef struct { uint16_t version,length; uint32_t cpu,gpu,mem; } SMCLimit;
typedef struct { uint32_t size,type; uint8_t attrs; } SMCInfo;
typedef struct { uint32_t key; SMCVersion version; SMCLimit limit; SMCInfo info;
    uint8_t result,status,command; uint32_t data; uint8_t bytes[32]; } SMCData;
static uint32_t fourCC(const char *s) { return ((uint32_t)s[0]<<24)|((uint32_t)s[1]<<16)|((uint32_t)s[2]<<8)|(uint32_t)s[3]; }
static BOOL smcRead(io_connect_t conn, SMCData *in, SMCData *out) {
    size_t size=sizeof(*out); memset(out,0,sizeof(*out));
    return IOConnectCallStructMethod(conn,2,in,sizeof(*in),out,&size)==KERN_SUCCESS && out->result==0;
}
static BOOL smcValue(io_connect_t conn,uint32_t key,SMCData *value) {
    SMCData in={0},info={0}; in.key=key; in.command=9;
    if(!smcRead(conn,&in,&info)||info.info.size>32)return NO;
    in.info=info.info; in.command=5;
    if(!smcRead(conn,&in,value))return NO;
    value->info=info.info; return YES;
}
static NSDictionary *temperatures(void) {
    io_iterator_t iter=0; io_connect_t conn=0;
    if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("AppleSMC"),&iter)!=KERN_SUCCESS)return @{};
    io_service_t service;
    while((service=IOIteratorNext(iter))){
        io_name_t name={0}; IORegistryEntryGetName(service,name);
        if(!strcmp(name,"AppleSMCKeysEndpoint"))IOServiceOpen(service,mach_task_self(),0,&conn);
        IOObjectRelease(service); if(conn)break;
    }
    IOObjectRelease(iter); if(!conn)return @{};
    double cpu=0,gpu=0; unsigned cpuCount=0,gpuCount=0;
    SMCData count={0};
    if(smcValue(conn,fourCC("#KEY"),&count)){
        uint32_t n=((uint32_t)count.bytes[0]<<24)|((uint32_t)count.bytes[1]<<16)|((uint32_t)count.bytes[2]<<8)|count.bytes[3];
        for(uint32_t i=0;i<MIN(n,10000);i++){
            SMCData in={0},out={0}; in.command=8; in.data=i;
            if(!smcRead(conn,&in,&out))continue;
            char name[5]={(out.key>>24)&255,(out.key>>16)&255,(out.key>>8)&255,out.key&255,0};
            BOOL isCPU=name[0]=='T'&&(name[1]=='p'||name[1]=='e'||name[1]=='s');
            BOOL isGPU=name[0]=='T'&&name[1]=='g';
            if(!isCPU&&!isGPU)continue;
            SMCData value={0};
            if(!smcValue(conn,out.key,&value)||value.info.size!=4||value.info.type!=fourCC("flt "))continue;
            float temp=0; memcpy(&temp,value.bytes,4);
            if(!isfinite(temp)||temp<=0||temp>150)continue;
            if(isCPU){cpu+=temp;cpuCount++;}else{gpu+=temp;gpuCount++;}
        }
    }
    IOServiceClose(conn);
    NSMutableDictionary *result=[NSMutableDictionary dictionary];
    if(cpuCount)result[@"cpu_c"]=@(cpu/cpuCount);
    if(gpuCount)result[@"gpu_c"]=@(gpu/gpuCount);
    result[@"cpu_sensor_count"]=@(cpuCount);result[@"gpu_sensor_count"]=@(gpuCount);
    result[@"source"]=@"AppleSMC · macmon sensor-family mapping";
    return result;
}
static NSDictionary *gpuUsage(void) {
    io_iterator_t iter=0;
    if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("AGXAccelerator"),&iter)!=KERN_SUCCESS)return @{};
    NSMutableDictionary *result=[NSMutableDictionary dictionary];io_service_t service;
    while((service=IOIteratorNext(iter))){
        CFTypeRef prop=IORegistryEntryCreateCFProperty(service,CFSTR("PerformanceStatistics"),kCFAllocatorDefault,0);
        if(prop&&CFGetTypeID(prop)==CFDictionaryGetTypeID()){
            NSDictionary *d=(__bridge NSDictionary *)prop;
            NSNumber *v=d[@"Device Utilization %"];
            if([v isKindOfClass:NSNumber.class]&&v.doubleValue>=0&&v.doubleValue<=100){result[@"used_percent"]=v;result[@"source"]=@"IORegistry · AGX device utilization";}
        }
        if(prop)CFRelease(prop);IOObjectRelease(service);if(result.count)break;
    }
    IOObjectRelease(iter);return result;
}
static BOOL ticks(host_cpu_load_info_data_t *data) {
    mach_msg_type_number_t count=HOST_CPU_LOAD_INFO_COUNT;mach_port_t host=mach_host_self();
    kern_return_t ok=host_statistics(host,HOST_CPU_LOAD_INFO,(host_info_t)data,&count);
    mach_port_deallocate(mach_task_self(),host);return ok==KERN_SUCCESS;
}
int main(void) {
 @autoreleasepool {
    double sampleStart=NSProcessInfo.processInfo.systemUptime;
    host_cpu_load_info_data_t before={0},after={0};BOOL cpuOK=ticks(&before);
    uint64_t total=0;size_t len=sizeof(total);sysctlbyname("hw.memsize",&total,&len,NULL,0);
    char chip[128]={0};len=sizeof(chip);sysctlbyname("machdep.cpu.brand_string",chip,&len,NULL,0);
    NSDictionary *temps=temperatures();NSDictionary *gpu=gpuUsage();
    usleep(250000);cpuOK=cpuOK&&ticks(&after);
    NSMutableDictionary *cpu=[NSMutableDictionary dictionary];
    if(cpuOK){uint64_t sum=0,idle=0;for(int i=0;i<CPU_STATE_MAX;i++){uint32_t delta=after.cpu_ticks[i]-before.cpu_ticks[i];sum+=delta;if(i==CPU_STATE_IDLE)idle=delta;}if(sum)cpu[@"used_percent"]=@(100.0*(sum-idle)/sum);}
    cpu[@"source"]=@"Mach CPU ticks · all logical cores";cpu[@"sample_seconds"]=@(NSProcessInfo.processInfo.systemUptime-sampleStart);
    vm_statistics64_data_t vm={0};mach_msg_type_number_t count=HOST_VM_INFO64_COUNT;mach_port_t host=mach_host_self();
    NSMutableDictionary *ram=[NSMutableDictionary dictionary];
    if(host_statistics64(host,HOST_VM_INFO64,(host_info64_t)&vm,&count)==KERN_SUCCESS&&total){
        uint64_t usedPages=(uint64_t)vm.active_count+vm.inactive_count+vm.wire_count+vm.speculative_count+vm.compressor_page_count;
        uint64_t reclaimable=(uint64_t)vm.purgeable_count+vm.external_page_count;
        uint64_t used=MIN(total,(usedPages>reclaimable?usedPages-reclaimable:0)*(uint64_t)getpagesize());
        ram[@"used_bytes"]=@(used);ram[@"total_bytes"]=@(total);ram[@"used_percent"]=@(100.0*used/total);ram[@"compressed_bytes"]=@((uint64_t)vm.compressor_page_count*getpagesize());
    }
    mach_port_deallocate(mach_task_self(),host);ram[@"source"]=@"Mach VM · app + wired + compressed, excluding file cache";
    NSArray *thermal=@[@"nominal",@"fair",@"serious",@"critical"];
    NSInteger pressure=NSProcessInfo.processInfo.thermalState;
    NSDictionary *output=@{@"version":@1,@"sampled_at":@([NSDate.date timeIntervalSince1970]),@"hardware":[NSString stringWithUTF8String:chip]?:@"Mac",@"cpu":cpu,@"gpu":gpu,@"ram":ram,@"temperature":temps,@"thermal_pressure":pressure>=0&&pressure<4?thermal[pressure]:@"unknown"};
    NSData *data=[NSJSONSerialization dataWithJSONObject:output options:0 error:nil];
    if(!data)return 1;fwrite(data.bytes,1,data.length,stdout);fputc('\n',stdout);
 }
 return 0;
}
