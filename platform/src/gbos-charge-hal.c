#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/wait.h>
/* Standard sustain thresholds where supported; this exact Motobook's fixed
 * conservation policy otherwise. No raw EC access, current-rate guessing,
 * fan/profile controls or charging writes during service registration. */
static const char *root="";
static int readnum(const char *path,int *value){char p[1024],buf[64],*end;snprintf(p,sizeof(p),"%s%s",root,path);int fd=open(p,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;ssize_t n=read(fd,buf,sizeof(buf)-1);close(fd);if(n<=0)return 0;buf[n]=0;errno=0;long x=strtol(buf,&end,10);while(*end=='\n'||*end==' '||*end=='\r')end++;if(errno||*end||x<0||x>100)return 0;*value=(int)x;return 1;}
static int writevalue(const char *path,int value){char p[1024],buf[32];snprintf(p,sizeof(p),"%s%s",root,path);int fd=open(p,O_WRONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;int n=snprintf(buf,sizeof(buf),"%d\n",value);int ok=write(fd,buf,(size_t)n)==n;close(fd);return ok;}
static int sustain(int lower,int upper){
 if(lower==-1&&upper==-1){lower=0;upper=100;}
 if(lower<0||upper<1||upper>100||lower>=upper)return -3;
 const char*start="/sys/class/power_supply/BAT0/charge_control_start_threshold";
 const char*end="/sys/class/power_supply/BAT0/charge_control_end_threshold";
 int oldstart,oldend;
 if(readnum(start,&oldstart)&&readnum(end,&oldend)){
  /* Preserve start<=end through intermediate states; roll back if either
   * write/readback fails. Never report a requested limit as applied blindly. */
  const char*first=upper<oldstart?start:end;const char*second=first==start?end:start;
  int a=first==start?lower:upper,b=first==start?upper:lower;
  if(!writevalue(first,a)||!writevalue(second,b)){
   writevalue(end,100);writevalue(start,oldstart);writevalue(end,oldend);return -5;
  }
  int actualstart,actualend;
  if(!readnum(start,&actualstart)||!readnum(end,&actualend)||actualstart!=lower||actualend!=upper){writevalue(end,100);writevalue(start,oldstart);writevalue(end,oldend);return -5;}
  return 0;
 }
 if(!((upper==100&&lower==0)||(upper==80&&lower>=75&&lower<80)))return -7;
 for(int i=0;i<8;i++){
  char node[160],driver[1024],path[1024],target[1024];int old,actual;
  snprintf(node,sizeof(node),"/sys/bus/acpi/devices/VPC2004:%02x/conservation_mode",i);
  snprintf(driver,sizeof(driver),"%s/sys/bus/acpi/devices/VPC2004:%02x/driver",root,i);
  ssize_t n=readlink(driver,target,sizeof(target)-1);if(n<=0)continue;target[n]=0;
  const char*base=strrchr(target,'/');base=base?base+1:target;
  if(strcmp(base,"gbos_motobook_charge"))continue;
  if(!readnum(node,&old)||old>1)continue;
  int wanted=upper==80;
  if(old==wanted)return 0;
  if(!writevalue(node,wanted)||!readnum(node,&actual)||actual!=wanted){writevalue(node,old);return -5;}
  snprintf(path,sizeof(path),"Motobook charging: firmware conservation %s; physical cap verification pending",wanted?"enabled":"disabled");puts(path);return 0;
 }
 return -7;
}
#ifdef CHARGE_BACKEND_TEST
int main(int argc,char**argv){if(argc!=4)return 2;root=argv[1];int r=sustain(atoi(argv[2]),atoi(argv[3]));printf("RESULT=%d\n",r);return r?1:0;}
#else
/* Small declarations of the platform Binder NDK C ABI; shipped AIDL union
 * layout/version/hash are pinned and checked by the image builder. */
typedef struct AIBinder AIBinder;typedef struct AIBinder_Class AIBinder_Class;
typedef struct AParcel AParcel;typedef struct AStatus AStatus;
typedef int32_t binder_status_t;typedef uint32_t transaction_code_t;
extern AIBinder_Class *AIBinder_Class_define(const char*,void*(*)(void*),void(*)(void*),binder_status_t(*)(AIBinder*,transaction_code_t,const AParcel*,AParcel*));
extern void AIBinder_Class_setOnDump(AIBinder_Class*,binder_status_t(*)(AIBinder*,int,const char**,uint32_t));
extern AIBinder *AIBinder_new(const AIBinder_Class*,void*);
extern void AIBinder_markVintfStability(AIBinder*);
extern uid_t AIBinder_getCallingUid(void);
extern binder_status_t AServiceManager_addService(AIBinder*,const char*);
extern void ABinderProcess_setThreadPoolMaxThreadCount(uint32_t);
extern void ABinderProcess_joinThreadPool(void);
extern binder_status_t AParcel_readInt32(const AParcel*,int32_t*);
extern binder_status_t AParcel_writeInt32(AParcel*,int32_t);
extern binder_status_t AParcel_writeString(AParcel*,const char*,int32_t);
extern int32_t AParcel_getDataPosition(const AParcel*);
extern int32_t AParcel_getDataSize(const AParcel*);
extern binder_status_t AParcel_setDataPosition(const AParcel*,int32_t);
extern AStatus *AStatus_newOk(void);
extern AStatus *AStatus_fromExceptionCodeWithMessage(int32_t,const char*);
extern binder_status_t AParcel_writeStatusHeader(AParcel*,const AStatus*);
extern void AStatus_delete(AStatus*);
static binder_status_t status(AParcel*out,int32_t code,const char*message){AStatus*s=code?AStatus_fromExceptionCodeWithMessage(code,message):AStatus_newOk();int r=AParcel_writeStatusHeader(out,s);AStatus_delete(s);return r;}
static void*create(void*arg){return arg;}static void destroy(void*arg){(void)arg;}
static binder_status_t dump(AIBinder*b,int fd,const char**args,uint32_t count){
 (void)b;(void)args;(void)count;
 dprintf(fd,"GBOS native charging backend; no raw Cros-EC dependency\n");
 dprintf(fd,"Battery charge aliases, when present, derive from ACPI energy and design voltage. CPU temperature is an actual Intel sensor.\n");
 dprintf(fd,"=== Plain Power HAL dump (collector -a intentionally omitted) ===\n");
 pid_t child=fork();
 if(child==0){dup2(fd,STDOUT_FILENO);dup2(fd,STDERR_FILENO);execl("/system/bin/timeout","timeout","3","/system/bin/dumpsys","android.hardware.power.IPower/default",(char*)NULL);_exit(127);}
 if(child>0){int status_code;while(waitpid(child,&status_code,0)<0&&errno==EINTR){}}
 dprintf(fd,"=== End plain Power HAL dump ===\n");return 0;
}
static binder_status_t transact(AIBinder*b,transaction_code_t code,const AParcel*in,AParcel*out){
 (void)b;
 if(code==16777215){int r=status(out,0,"");return r?r:AParcel_writeInt32(out,1);}
 if(code==16777214){int r=status(out,0,"");return r?r:AParcel_writeString(out,"aba939fd9c5f7bbfe96770e7ff3bc7c9859a5725",40);}
 if(code!=1)return -74;
 uid_t uid=AIBinder_getCallingUid();if(uid!=0&&uid%100000!=1000)return status(out,-1,"Only the system charging policy may change charging");
 int32_t present,tag;
 if(AParcel_readInt32(in,&present)||present!=1||AParcel_readInt32(in,&tag))return status(out,-3,"Invalid charging strategy");
 if(tag==1)return status(out,-7,"Reduced-rate charging has no supported native control");
 if(tag!=0||AParcel_readInt32(in,&present)||present!=1)return status(out,-3,"Invalid sustain strategy");
 int32_t start=AParcel_getDataPosition(in),size,lower,upper;
 if(AParcel_readInt32(in,&size)||size<12||size>1024||start<0||start>AParcel_getDataSize(in)-size||AParcel_readInt32(in,&lower)||AParcel_readInt32(in,&upper))return status(out,-3,"Invalid sustain parameters");
 if(AParcel_setDataPosition(in,start+size)||AParcel_getDataPosition(in)!=AParcel_getDataSize(in))return status(out,-3,"Unexpected charging data");
 int r=sustain(lower,upper);
 return status(out,r,r==-7?"This charging limit has no supported native backend":r?"Native charging control rejected the request":"");
}
int main(void){
 const char*descriptor="com.android.desktop.power.IDesktopPowerChargeControl";
 AIBinder_Class*cls=AIBinder_Class_define(descriptor,create,destroy,transact);if(!cls)return 1;
 AIBinder_Class_setOnDump(cls,dump);
 AIBinder*b=AIBinder_new(cls,NULL);if(!b)return 1;AIBinder_markVintfStability(b);
 ABinderProcess_setThreadPoolMaxThreadCount(2);
 if(AServiceManager_addService(b,"com.android.desktop.power.IDesktopPowerChargeControl/default"))return 1;
 puts("GBOS native charging HAL registered; no charging mode changed at startup");
 ABinderProcess_joinThreadPool();return 0;
}
#endif
