#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <glob.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sched.h>
#include <cpuid.h>
#include <stdint.h>
/* Read hardware topology and existing controls; emit JSON only. The Power HAL
 * owns all subsequent reversible node writes. No thermal/frequency limits. */
static const char *root="";
static char nodes[65536],actions[65536];static size_t nn,na;static int nc,ac;
static int readval(const char *path,char *out,size_t size){char p[4096];snprintf(p,sizeof(p),"%s%s",root,path);FILE*f=fopen(p,"r");if(!f)return 0;size_t n=fread(out,1,size-1,f);fclose(f);out[n]=0;while(n&&strchr(" \n\r\t",out[n-1]))out[--n]=0;return n>0;}
static int exists(const char *path){char p[4096];struct stat st;snprintf(p,sizeof(p),"%s%s",root,path);return stat(p,&st)==0&&S_ISREG(st.st_mode);}
static int token(const char*s,const char*t){size_t n=strlen(t);for(const char*p=s;(p=strstr(p,t));p++){if((p==s||p[-1]==' ')&&(p[n]==0||p[n]==' '))return 1;}return 0;}
static int safe(const char*s){return strspn(s,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/-., ")==strlen(s);}
static void node(const char *name,const char *path,const char *values,int def,int prop){int n=snprintf(nodes+nn,sizeof(nodes)-nn,"%s{\"Name\":\"%s\",\"Path\":\"%s\",\"Values\":[%s],\"DefaultIndex\":%d,\"ResetOnInit\":true%s}",nc++?",":"",name,path,values,def,prop?",\"Type\":\"Property\"":"");if(n<0||(size_t)n>=sizeof(nodes)-nn)exit(3);nn+=n;}
static void action(const char*hint,const char*name,const char*value,int duration){int n=snprintf(actions+na,sizeof(actions)-na,"%s{\"PowerHint\":\"%s\",\"Node\":\"%s\",\"Duration\":%d,\"Value\":\"%s\"}",ac++?",":"",hint,name,duration,value);if(n<0||(size_t)n>=sizeof(actions)-na)exit(3);na+=n;}
static int parselist(const char*list,int*set){char copy[2048];if(strlen(list)>=sizeof(copy)||strspn(list,"0123456789,-")!=strlen(list))return 0;strcpy(copy,list);char*save=NULL;for(char*t=strtok_r(copy,",",&save);t;t=strtok_r(NULL,",",&save)){int a,b;char extra;if(sscanf(t,"%d-%d%c",&a,&b,&extra)==2){}else if(sscanf(t,"%d%c",&a,&extra)==1)b=a;else return 0;if(a<0||b<a||b>=256)return 0;for(int i=a;i<=b;i++)set[i]=1;}return 1;}
static void cpulist(const int*set,char*out,size_t size){out[0]=0;for(int i=0;i<256;i++)if(set[i]){char v[12];snprintf(v,sizeof(v),"%s%d",out[0]?",":"",i);if(strlen(out)+strlen(v)+1>=size)exit(3);strcat(out,v);}}
/* Linux topology types use1 for Atom; Intel CPUID leaf1A uses0x20.
 * If sysfs lacks the type, inspect CPUID on each real CPU, restoring our own
 * affinity. This is identification only: no workload, clock or limit write. */
static int atom_cpu(int cpu){
 if(*root)return 0; /* Offline fixtures never inspect their host's CPU. */
 unsigned a,b,c,d;if(!__get_cpuid(0,&a,&b,&c,&d)||a<0x1a)return 0;
 char vendor[13];memcpy(vendor,&b,4);memcpy(vendor+4,&d,4);memcpy(vendor+8,&c,4);vendor[12]=0;
 if(strcmp(vendor,"GenuineIntel"))return 0;
 cpu_set_t saved,one;if(cpu>=CPU_SETSIZE||sched_getaffinity(0,sizeof(saved),&saved))return 0;
 CPU_ZERO(&one);CPU_SET(cpu,&one);if(sched_setaffinity(0,sizeof(one),&one))return 0;
 __cpuid_count(0x1a,0,a,b,c,d);int atom=(a>>24)==0x20;
 if(sched_setaffinity(0,sizeof(saved),&saved))exit(5);
 return atom;
}
int main(int argc,char**argv){
 if(argc==3&&strcmp(argv[1],"--root")==0)root=argv[2];else if(argc!=1)return 2;
 char online[2048];if(!readval("/sys/devices/system/cpu/online",online,sizeof(online))||strspn(online,"0123456789,-")!=strlen(online))return 4;
 int all[256]={0},efficient[256]={0};if(!parselist(online,all))return 4;
 /* Hybrid perf PMUs name the efficient cores directly (Arrow Lake-H: Atom
  * E-cores plus low-power E-cores). Topology/CPUID remain the fallback. */
 int pmu[256]={0},pmuseen=0;const char*pmus[]={"/sys/devices/cpu_atom/cpus","/sys/devices/cpu_lowpower/cpus"};
 for(int i=0;i<2;i++){char v[2048];if(readval(pmus[i],v,sizeof(v))&&parselist(v,pmu))pmuseen=1;}
 int total=0,etotal=0;for(int i=0;i<256;i++)if(all[i]){total++;if(pmuseen){if(pmu[i]){efficient[i]=1;etotal++;}continue;}char path[256],v[64];snprintf(path,sizeof(path),"/sys/devices/system/cpu/cpu%d/topology/core_type",i);long type=readval(path,v,sizeof(v))?strtol(v,NULL,0):0;if(type==1||type==0x20||(!type&&atom_cpu(i))){efficient[i]=1;etotal++;}}
 if(!total)return 4;
 /* All-efficient or no-efficient topologies keep every CPU for background. */
 if(etotal==total)etotal=0;
 char cpus[2048],ecpus[2048];cpulist(all,cpus,sizeof(cpus));cpulist(etotal?efficient:all,ecpus,sizeof(ecpus));
 fprintf(stderr,"Online CPUs=%s; background CPUs=%s; Intel Atom topology entries=%d\n",cpus,ecpus,etotal);
 node("ProfileState","vendor.powerhal.gbos.profile","\"battery\",\"boost\",\"performance\"",2,1);
 action("LOW_POWER","ProfileState","battery",0);action("LAUNCH","ProfileState","boost",1000);action("INTERACTION","ProfileState","boost",200);
 const char*groups[]={"top-app","foreground","foreground_window","camera-daemon","background","system-background","restricted"};
 for(int i=0;i<7;i++){char path[256],name[64],values[4096];snprintf(path,sizeof(path),"/dev/cpuset/%s/cpus",groups[i]);if(!exists(path))continue;snprintf(name,sizeof(name),"CpuSet%d",i);snprintf(values,sizeof(values),"\"%s\"",i>=4?ecpus:cpus);node(name,path,values,0,0);action("LOW_POWER",name,i>=4?ecpus:cpus,0);}
 const char*u="/dev/cpuctl/top-app/cpu.uclamp.min";
 if(exists(u)){node("TopAppUclamp",u,"\"0\",\"15\",\"25\"",0,0);action("LOW_POWER","TopAppUclamp","0",0);action("LAUNCH","TopAppUclamp","25",1000);action("INTERACTION","TopAppUclamp","15",200);}
 /* Xe render GT: finite minimum-frequency floors from the hardware's own RPe
  * and RP0 values. The boot minimum stays the default; no maximum is changed. */
 char pattern[4096];snprintf(pattern,sizeof(pattern),"%s/sys/class/drm/card*/device/tile0/gt0/freq0/min_freq",root);glob_t gpus={0};
 if(glob(pattern,0,NULL,&gpus)==0&&gpus.gl_pathc){
  char path[4096],dir[4096],rpe[32],rp0[32],cur[32],max[32];snprintf(path,sizeof(path),"%s",gpus.gl_pathv[0]+strlen(root));snprintf(dir,sizeof(dir),"%s",path);*strrchr(dir,'/')=0;
  char p1[4200],p2[4200],p3[4200];snprintf(p1,sizeof(p1),"%s/rpe_freq",dir);snprintf(p2,sizeof(p2),"%s/rp0_freq",dir);snprintf(p3,sizeof(p3),"%s/max_freq",dir);
  if(safe(path)&&readval(p1,rpe,sizeof(rpe))&&readval(p2,rp0,sizeof(rp0))&&readval(p3,max,sizeof(max))&&readval(path,cur,sizeof(cur))&&strspn(rpe,"0123456789")==strlen(rpe)&&strspn(rp0,"0123456789")==strlen(rp0)&&strspn(cur,"0123456789")==strlen(cur)&&strspn(max,"0123456789")==strlen(max)){
   long e=atol(rpe),z=atol(rp0),c=atol(cur),m=atol(max);
   if(c>0&&c<=e&&e<=z&&z<=m){
    /* Higher floors first so a launch outranks an interaction. */
    const char*choices[]={rp0,rpe,cur};const char*unique[3];int count=0,def=0;char vals[256]="";
    for(int j=0;j<3;j++){int found=0;for(int k=0;k<count;k++)if(!strcmp(unique[k],choices[j]))found=1;if(found)continue;unique[count]=choices[j];if(!strcmp(choices[j],cur))def=count;snprintf(vals+strlen(vals),sizeof(vals)-strlen(vals),"%s\"%s\"",count?",":"",choices[j]);count++;}
    node("GpuMinFreq",path,vals,def,0);action("LAUNCH","GpuMinFreq",rp0,1000);action("INTERACTION","GpuMinFreq",rpe,200);
    fprintf(stderr,"Xe GT0 %s: default=%s, interaction=%s, launch=%s MHz (max %s unchanged)\n",path,cur,rpe,rp0,max);
   }
  }
 }globfree(&gpus);
 snprintf(pattern,sizeof(pattern),"%s/sys/devices/system/cpu/cpufreq/policy*/energy_performance_available_preferences",root);glob_t matches={0};
 if(glob(pattern,0,NULL,&matches)==0){for(size_t i=0;i<matches.gl_pathc;i++){
  const char*rel=matches.gl_pathv[i]+strlen(root);char avail[1024],path[4096],name[64];if(!readval(rel,avail,sizeof(avail)))continue;
  snprintf(path,sizeof(path),"%s",rel);char*tail=strrchr(path,'/');if(!tail)continue;strcpy(tail+1,"energy_performance_preference");if(!exists(path)||!safe(path))continue;
  const char*balanced=token(avail,"performance")?"performance":token(avail,"balance_performance")?"balance_performance":token(avail,"balance_power")?"balance_power":NULL;
  if(!balanced)continue;
  const char*energy=token(avail,"balance_power")?"balance_power":balanced;
  const char*battery=token(avail,"power")?"power":energy;const char*boost=balanced;
  snprintf(name,sizeof(name),"Epp%zu",i);char vals[1024]="";int def=0,count=0;
  /* Earlier values have higher libperfmgr priority: Battery Saver must win
   * over interaction/launch, which must win over media's energy preference.
   * Default is a hardware preference, never a fixed clock or turbo floor. */
  const char*choices[]={battery,boost,energy};const char*unique[3];
  for(int j=0;j<3;j++){int found=0;for(int k=0;k<count;k++)if(!strcmp(unique[k],choices[j]))found=1;if(found)continue;unique[count]=choices[j];if(!strcmp(choices[j],balanced))def=count;snprintf(vals+strlen(vals),sizeof(vals)-strlen(vals),"%s\"%s\"",count?",":"",choices[j]);count++;}
  node(name,path,vals,def,0);action("LOW_POWER",name,battery,0);action("LAUNCH",name,boost,1000);action("INTERACTION",name,boost,200);action("SUSTAINED_PERFORMANCE",name,balanced,0);action("PROFILE_MEDIA_PLAYBACK",name,energy,0);action("PROFILE_VIDEO_PLAYBACK",name,energy,0);
  fprintf(stderr,"EPP %s: default=%s, boost=%s, battery=%s\n",path,balanced,boost,battery);
 }}globfree(&matches);
 printf("{\"Nodes\":[%s],\"Actions\":[%s]",nodes,actions);
 /* ADPF controls individual session threads through sched_setattr. Its scale
  * is 0..1024 (unlike the cgroup percentage file above). Start/reset at zero,
  * use a bounded proportional controller, and leave GPU/heuristic boosts off.
  * The stock desktop JSON also omitted ADPF; this is new port support. */
 if(exists(u)){
  printf(",\"AdpfConfig\":[{\"Name\":\"INTEL_BALANCED\","
   "\"PID_On\":true,\"PID_Po\":2.0,\"PID_Pu\":1.0,\"PID_I\":0.0,"
   "\"PID_I_Init\":0,\"PID_I_High\":0,\"PID_I_Low\":0,"
   "\"PID_Do\":0.0,\"PID_Du\":0.0,\"UclampMin_On\":true,"
   "\"UclampMin_Init\":0,\"UclampMin_High\":384,\"UclampMin_Low\":0,"
   "\"UclampMin_LoadUp\":256,\"UclampMin_LoadReset\":0,"
   "\"SamplingWindow_P\":1,\"SamplingWindow_I\":1,\"SamplingWindow_D\":1,"
   "\"ReportingRateLimitNs\":16666666,\"StaleTimeFactor\":4.0,"
   "\"TargetTimeFactor\":1.0,\"GpuBoost\":false,"
   "\"UclampMax_EfficientBase\":512,\"UclampMax_EfficientOffset\":128}]");
  fprintf(stderr,"ADPF Intel CPU sessions configured: clamp 0..384/1024, no persistent floor, GPU boost disabled\n");
 }
 puts("}");
 return ferror(stdout)?5:0;
}
