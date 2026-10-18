/* Read-only HAL quirk for the observed Motobook 83NY / BE02T connection.
 * Never writes sysfs, requests a role swap, or changes electrical power.
 * Original sysfs remains visible to every process without this preload.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/syscall.h>
#ifndef GBOS_SYS
#define GBOS_SYS "/sys"
#endif
static int raw_open(const char *p,int flags,mode_t mode){return syscall(SYS_openat,AT_FDCWD,p,flags,mode);}
#include "gbos-usb-audio-quirk.h"
static int quirk_active(void){return gb_usb_audio_only(GBOS_SYS,1);}
static int ends(const char *p,const char *tail){size_t a=strlen(p),b=strlen(tail);return a>=b&&!strcmp(p+a-b,tail);}
static const char *replacement(const char *p,int flags){
 if(!p||strncmp(p,GBOS_SYS "/",sizeof(GBOS_SYS))||(flags&O_ACCMODE)!=O_RDONLY)return NULL;
 const char *r=NULL;
 if(ends(p,"/typec/port1/power_role"))r="[source] sink\n";
 else if(ends(p,"/typec/port1/data_role"))r="[host] device\n";
 else if(ends(p,"/power_supply/ucsi-source-psy-USBC000:002/online"))r="0\n";
 return r&&quirk_active()?r:NULL;
}
static int substitute(const char *data,int flags){
 int fd=syscall(SYS_memfd_create,"gbos-usb-role",(flags&O_CLOEXEC)?1:0);
 if(fd<0)return -1;
 size_t n=strlen(data);if(syscall(SYS_write,fd,data,n)!=(ssize_t)n||syscall(SYS_lseek,fd,0,SEEK_SET)<0){syscall(SYS_close,fd);return -1;}
 return fd;
}
static mode_t mode_arg(int flags,va_list ap){return ((flags&O_CREAT)||(flags&O_TMPFILE)==O_TMPFILE)?(mode_t)va_arg(ap,int):0;}
int open(const char *p,int flags,...){va_list ap;va_start(ap,flags);mode_t mode=mode_arg(flags,ap);va_end(ap);const char *r=replacement(p,flags);if(r){int fd=substitute(r,flags);if(fd>=0)return fd;}return raw_open(p,flags,mode);}
int open64(const char *p,int flags,...){va_list ap;va_start(ap,flags);mode_t mode=mode_arg(flags,ap);va_end(ap);return open(p,flags,mode);}
int openat(int dirfd,const char *p,int flags,...){va_list ap;va_start(ap,flags);mode_t mode=mode_arg(flags,ap);va_end(ap);const char *r=p[0]=='/'?replacement(p,flags):NULL;if(r){int fd=substitute(r,flags);if(fd>=0)return fd;}return syscall(SYS_openat,dirfd,p,flags,mode);}
int openat64(int dirfd,const char *p,int flags,...){va_list ap;va_start(ap,flags);mode_t mode=mode_arg(flags,ap);va_end(ap);return openat(dirfd,p,flags,mode);}
int __open_2(const char *p,int flags){return open(p,flags,0);}
int __openat_2(int dirfd,const char *p,int flags){return openat(dirfd,p,flags,0);}
