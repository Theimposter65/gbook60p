#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <linux/netlink.h>
#include <poll.h>
#include <time.h>
#include "gbos-usb-audio-quirk.h"
#ifdef GBOS_ANDROID_HEALTH
#include <android/binder_ibinder.h>
#include <android/binder_parcel.h>
#include <android/binder_status.h>
/* Exported by this build's pinned libbinder_ndk; platform API, not app SDK. */
extern AIBinder* AServiceManager_checkService(const char*instance);
static void* health_create(void*p){return p;}
static void health_destroy(void*p){(void)p;}
static binder_status_t health_unexpected(AIBinder*b,transaction_code_t c,const AParcel*i,AParcel*o){(void)b;(void)c;(void)i;(void)o;return STATUS_UNKNOWN_TRANSACTION;}
static int health_refresh(void){
 static AIBinder_Class* cls;
 if(!cls)cls=AIBinder_Class_define("android.hardware.health.IHealth",health_create,health_destroy,health_unexpected);
 AIBinder*b=AServiceManager_checkService("android.hardware.health.IHealth/default");if(!b)return 0;
 int ok=0;AParcel*in=NULL,*out=NULL;AStatus*status=NULL;
 if(AIBinder_associateClass(b,cls)&&AIBinder_prepareTransaction(b,&in)==STATUS_OK){
  /* Stable IHealth.update(), third declared method; callback refresh only. */
  if(AIBinder_transact(b,FIRST_CALL_TRANSACTION+2,&in,&out,0)==STATUS_OK&&
     AParcel_readStatusHeader(out,&status)==STATUS_OK&&AStatus_isOk(status))ok=1;
 }
 if(in)AParcel_delete(in);
 if(out)AParcel_delete(out);
 if(status)AStatus_delete(status);
 AIBinder_decStrong(b);return ok;
}
#else
static int health_refresh(void){return 0;}
#endif
/* Read-only hardware inputs. Only derived values/configuration in retained
 * RAM are written. Never invent a battery temperature or charge measurement. */
static int text(const char *dir,const char *name,char *buf,size_t cap){
 char path[PATH_MAX];if(snprintf(path,sizeof(path),"%s/%s",dir,name)>=(int)sizeof(path))return 0;
 FILE*f=fopen(path,"r");if(!f)return 0;size_t n=fread(buf,1,cap-1,f);fclose(f);buf[n]=0;
 while(n&&strchr(" \t\r\n",buf[n-1]))buf[--n]=0;
 return n>0;
}
static int number(const char *dir,const char *name,int64_t *v){char b[128],*end;if(!text(dir,name,b,sizeof(b)))return 0;errno=0;long long x=strtoll(b,&end,10);if(errno||*end)return 0;*v=x;return 1;}
static int present(const char *dir,const char*name){char p[PATH_MAX];snprintf(p,sizeof(p),"%s/%s",dir,name);return access(p,F_OK)==0;}
static int strict_text(const char *dir,const char*name,char*buf,size_t cap){
 char path[PATH_MAX];if(snprintf(path,sizeof(path),"%s/%s",dir,name)>=(int)sizeof(path))return 0;
 int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;
 ssize_t n=read(fd,buf,cap-1);close(fd);if(n<=0)return 0;buf[n]=0;
 while(n&&strchr(" \t\r\n",buf[n-1]))buf[--n]=0;
 return n>0;
}
static int check_battery_view(const char*dir){
 char buf[128],*end;
 if(!strict_text(dir,"type",buf,sizeof(buf))||strcmp(buf,"Battery"))return 10;
 if(!strict_text(dir,"present",buf,sizeof(buf))||(strcmp(buf,"0")&&strcmp(buf,"1")))return 10;
 if(!strict_text(dir,"capacity",buf,sizeof(buf)))return 10;
 errno=0;long capacity=strtol(buf,&end,10);if(errno||*end||capacity<0||capacity>100)return 10;
 if(!strict_text(dir,"status",buf,sizeof(buf)))return 10;
 if(strcmp(buf,"Charging")&&strcmp(buf,"Discharging")&&strcmp(buf,"Full")&&strcmp(buf,"Not charging")&&strcmp(buf,"Unknown"))return 10;
 const char*fields[]={"voltage_now","cycle_count","energy_now","energy_full","charge_now","charge_full","charge_full_design","charge_counter","current_now"};
 for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);i++){
  if(!present(dir,fields[i]))continue;
  if(!strict_text(dir,fields[i],buf,sizeof(buf)))return 10;
  errno=0;(void)strtoll(buf,&end,10);if(errno||*end)return 10;
 }
 return 0;
}
static int store(const char *dir,const char *name,int64_t value){
 int64_t old;if(number(dir,name,&old)&&old==value)return 1;
 char path[PATH_MAX],buf[64];snprintf(path,sizeof(path),"%s/%s",dir,name);
 /* Keep the inode stable for mounted views and HAL readers holding an FD.
  * One pwrite publishes a complete number; never replace it by rename. */
 int n=snprintf(buf,sizeof(buf),"%lld\n",(long long)value);
 int fd=open(path,O_WRONLY|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0444);if(fd<0)return 0;
 int ok=pwrite(fd,buf,(size_t)n,0)==n&&ftruncate(fd,n)==0;close(fd);return ok;
}
static int battery(const char *src,const char *view){
 char type[64],status[64];int64_t v,now,full,design,power,actual;
 if(!text(src,"type",type,sizeof(type))||strcmp(type,"Battery"))return 3;
 if(!number(src,"voltage_min_design",&v)||v<5000000||v>30000000)return 4;
 if(!number(src,"energy_now",&now)||!number(src,"energy_full",&full)||!number(src,"energy_full_design",&design))return 4;
 if(now<0||full<=0||design<=0||now>250000000||full>250000000||design>250000000)return 4;
 int64_t charge[]={now*1000000/v,full*1000000/v,design*1000000/v,now*1000000/v};
 const char*names[]={"charge_now","charge_full","charge_full_design","charge_counter"};
 for(int i=0;i<4;i++)if(!present(src,names[i])&&!store(view,names[i],charge[i]))return 5;
 if(!present(src,"current_now")){
  if(!number(src,"power_now",&power)||power<0||power>250000000||!number(src,"voltage_now",&actual)||actual<5000000||actual>30000000||!text(src,"status",status,sizeof(status)))return 6;
  int64_t current=power*1000000/actual;
  if(!strcmp(status,"Discharging"))current=-current;
  else if(!strcmp(status,"Full")||!strcmp(status,"Not charging"))current=0;
  else if(strcmp(status,"Charging"))return 6;
  if(!store(view,"current_now",current))return 5;
 }
 return 0;
}
static int thermal(const char *root,const char *output){
 char type[128],dir[PATH_MAX],json[8192];size_t pos=0;int count=0;
 pos+=(size_t)snprintf(json+pos,sizeof(json)-pos,"{\"Comment\":\"Read-only native Intel telemetry; no cooling-device or trip-point writes\",\"Sensors\":[");
 for(int i=0;i<128;i++){
  snprintf(dir,sizeof(dir),"%s/sys/class/thermal/thermal_zone%d",root,i);int64_t temp;
  if(!text(dir,"type",type,sizeof(type))||strcmp(type,"x86_pkg_temp")||!number(dir,"temp",&temp)||temp<0||temp>125000)continue;
  int n=snprintf(json+pos,sizeof(json)-pos,"%s{\"Name\":\"intel-package-%d\",\"Type\":\"CPU\",\"TempPath\":\"/sys/class/thermal/thermal_zone%d/temp\",\"Multiplier\":0.001,\"SendCallback\":false,\"SendPowerHint\":false}",count?",":"",i,i);
  if(n<0||(size_t)n>=sizeof(json)-pos)return 7;
  pos+=(size_t)n;count++;
 }
 if(!count)return 8;
 snprintf(json+pos,sizeof(json)-pos,"],\"CoolingDevices\":[],\"PowerRails\":[]}\n");
 FILE*f=fopen(output,"w");if(!f)return 5;int ok=fputs(json,f)>=0;if(fclose(f))ok=0;
 return ok?0:5;
}
static int usb_online(const char *source,const char *rolepath,const char *output,int notify){
 char role[128],scope[64],old[32];int64_t online;
 if(!text(source,"scope",scope,sizeof(scope))||strcmp(scope,"Device")||!number(source,"online",&online)||online<0||online>1)return 9;
 FILE*f=fopen(rolepath,"r");if(!f)return 9;size_t n=fread(role,1,sizeof(role)-1,f);fclose(f);role[n]=0;
 while(n&&strchr(" \n\r\t",role[n-1]))role[--n]=0;
 int sink=strstr(role,"[sink]")!=NULL||!strcmp(role,"sink");
 int source_role=strstr(role,"[source]")!=NULL||!strcmp(role,"source");
 if(!sink&&!source_role)return 9;
 int value=online&&sink;
 if(strstr(rolepath,"/class/typec/port1/power_role")){
  const char*marker=strstr(rolepath,"/class/typec/");char sysroot[PATH_MAX];size_t len=(size_t)(marker-rolepath);
  if(len<sizeof(sysroot)){memcpy(sysroot,rolepath,len);sysroot[len]=0;if(gb_usb_audio_only(sysroot,1))value=0;}
 }
 f=fopen(output,"r");int same=f&&fgets(old,sizeof(old),f)&&atoi(old)==value;if(f)fclose(f);
 if(same)return 0;
 f=fopen(output,"w");if(!f)return 5;int ok=fprintf(f,"%d\n",value)>0;if(fclose(f))ok=0;
 if(!ok)return 5;
 chmod(output,0444);
 if(notify){char event[PATH_MAX];snprintf(event,sizeof(event),"%s/uevent",source);f=fopen(event,"w");if(f){fputs("change\n",f);fclose(f);}}
 return 0;
}
static int relevant_event(const char*b,size_t n){
 for(size_t p=0;p<n;){size_t len=strnlen(b+p,n-p);if(len==n-p)break;
  if(!strcmp(b+p,"SUBSYSTEM=power_supply")||!strcmp(b+p,"SUBSYSTEM=typec")||!strcmp(b+p,"SUBSYSTEM=usb"))return 1;
  p+=len+1;
 }return 0;
}
static long long monotonic_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (long long)t.tv_sec*1000+t.tv_nsec/1000000;}
static int watch_platform(const char *base){
 int fd=socket(AF_NETLINK,SOCK_DGRAM|SOCK_CLOEXEC,NETLINK_KOBJECT_UEVENT);
 if(fd>=0){struct sockaddr_nl address={.nl_family=AF_NETLINK,.nl_pid=0,.nl_groups=1};if(bind(fd,(struct sockaddr*)&address,sizeof(address))){close(fd);fd=-1;}}
 long long next=0,refresh=0;int last_error=-1;
 for(;;){
  long long tick=monotonic_ms();
  if(tick<next&&fd>=0){
   struct pollfd pfd={.fd=fd,.events=POLLIN};int r=poll(&pfd,1,(int)(next-tick));
   if(r<0&&errno==EINTR)continue;
   if(r>0){char buf[8192];int relevant=0;ssize_t n;
    while((n=recv(fd,buf,sizeof(buf),MSG_DONTWAIT))>0)if(relevant_event(buf,(size_t)n))relevant=1;
    if(!relevant)continue;
   }
  }
  char src[PATH_MAX],view[PATH_MAX],role[PATH_MAX],cfg[PATH_MAX];
  if(present(base,"battery-ready")){snprintf(src,sizeof(src),"%s/battery-source",base);snprintf(view,sizeof(view),"%s/battery-view",base);int r=battery(src,view);if(r&&r!=last_error)fprintf(stderr,"Battery conversion unavailable (%d); native inputs retained\n",r);last_error=r;}
  int online_changed=0;
  for(int i=0;i<2;i++){
   snprintf(cfg,sizeof(cfg),"usb%d-role",i);if(!text(base,cfg,role,sizeof(role)))continue;
   snprintf(src,sizeof(src),"%s/usb%d-source",base,i);snprintf(view,sizeof(view),"%s/usb%d-online",base,i);
   int64_t before=-1,after=-1;snprintf(cfg,sizeof(cfg),"usb%d-online",i);(void)number(base,cfg,&before);
   (void)usb_online(src,role,view,1);
   (void)number(base,cfg,&after);
   if(before!=after)online_changed=1;
  }
  /* Schedule real HealthInfo callbacks; no fake capacity/plugged properties.
   * Deadline uses monotonic time, so unrelated events cannot starve updates. */
  tick=monotonic_ms();if(tick>=refresh||online_changed){(void)health_refresh();refresh=tick+30000;}
  next=tick+(present(base,"battery-ready")?5000:30000);
  if(fd<0)sleep(5);
 }
 return 0;
}
int main(int argc,char**argv){
 if(argc==3&&!strcmp(argv[1],"--check-battery-view"))return check_battery_view(argv[2]);
 if(argc==5&&!strcmp(argv[1],"--usb-online"))return usb_online(argv[2],argv[3],argv[4],0);
 if(argc==3&&!strcmp(argv[1],"--watch-platform"))return watch_platform(argv[2]);
 if(argc!=4)return 2;
 if(!strcmp(argv[1],"--thermal"))return thermal(argv[2],argv[3]);
 if(!strcmp(argv[1],"--battery"))return battery(argv[2],argv[3]);
 if(!strcmp(argv[1],"--watch-battery")){
  for(;;){int r=battery(argv[2],argv[3]);if(r)fprintf(stderr,"Battery telemetry update unavailable (%d); no invented values\n",r);sleep(r?30:5);}
 }
 return 2;
}
