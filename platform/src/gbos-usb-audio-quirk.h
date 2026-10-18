/* Exact direct-attached BE02T headset; never writes electrical/data roles.
 * bmAttributes a0 is bus powered with remote wake, not a self-powered device.
 * This UCSI implementation also reports PD/sink for the known audio-only
 * headset, so those two fields cannot be used to decide that it is a charger.
 */
#include <glob.h>
#include <sys/syscall.h>
static int gb_usb_read(const char*path,char*buf,size_t cap){
 int fd=(int)syscall(SYS_openat,AT_FDCWD,path,O_RDONLY|O_CLOEXEC,0);if(fd<0)return 0;
 ssize_t n=syscall(SYS_read,fd,buf,cap-1);syscall(SYS_close,fd);if(n<=0)return 0;buf[n]=0;
 while(n&&strchr(" \t\r\n",buf[n-1]))buf[--n]=0;
 return n>0;
}
static int gb_usb_equals(const char*sys,const char*tail,const char*value){char p[4096],b[128];if(snprintf(p,sizeof(p),"%s/%s",sys,tail)>=(int)sizeof(p))return 0;return gb_usb_read(p,b,sizeof(b))&&!strcmp(b,value);}
static int gb_usb_audio_only(const char*sys,int port){
 if(port!=1||!gb_usb_equals(sys,"class/dmi/id/product_name","83NY")||
    !gb_usb_equals(sys,"bus/usb/devices/3-2/idVendor","2a70")||
    !gb_usb_equals(sys,"bus/usb/devices/3-2/idProduct","1881")||
    !gb_usb_equals(sys,"bus/usb/devices/3-2/product","BE02T"))return 0;
 char p[4096],b[512],*end;if(snprintf(p,sizeof(p),"%s/bus/usb/devices/3-2/bmAttributes",sys)>=(int)sizeof(p))return 0;
 if(!gb_usb_read(p,b,sizeof(b)))return 0;
 unsigned long attr=strtoul(b,&end,16);if(*end||attr>255||!(attr&0x80)||(attr&0x40))return 0;
 if(snprintf(p,sizeof(p),"%s/bus/usb/devices/3-2",sys)>=(int)sizeof(p))return 0;
 ssize_t n=readlink(p,b,sizeof(b)-1);if(n<=0)return 0;b[n]=0;
 if(!strstr(b,"0000:00:14.0/usb3/3-2"))return 0;
 if(snprintf(p,sizeof(p),"%s/bus/usb/devices/3-2:*/bInterfaceClass",sys)>=(int)sizeof(p))return 0;
 glob_t g={0};int audio=0,hub=0;
 if(glob(p,0,NULL,&g)==0)for(size_t i=0;i<g.gl_pathc;i++)if(gb_usb_read(g.gl_pathv[i],b,sizeof(b))){
  unsigned long cls=strtoul(b,&end,16);if(!*end&&cls==1)audio=1;if(!*end&&cls==9)hub=1;
 }
 globfree(&g);return audio&&!hub;
}
