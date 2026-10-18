/* Read-only ALSA inspection and speaker XML generation. No mixer write ioctl,
 * PCM playback/recording, raw HDA verbs, driver changes or background loop. */
#include <sound/asound.h>
#include <sound/tlv.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>

/* Return the greatest value at/below the requested attenuation. Reject
 * unknown TLVs rather than guessing a raw scale or allowing positive gain. */
static long scale_value(long lo,long hi,const unsigned int *tlv,size_t words,int cap) {
 if(words<4 || tlv[0]!=SNDRV_CTL_TLVT_DB_SCALE || tlv[1]!=8 || cap>0 || lo<0 || hi<lo || hi>1000000) return LONG_MIN;
 long min=(int)tlv[2],step=tlv[3]&0xffff;
 if(step<=0 || min>cap || min < -200000 || min>0) return LONG_MIN;
 long value=lo+(cap-min)/step;
 if(value>hi)value=hi;
 if(value<lo || min+(value-lo)*step>cap) return LONG_MIN;
 /* A mute-at-minimum step is not a useful speaker initialization. */
 if((tlv[3]&0x10000) && value==lo) return LONG_MIN;
 return value;
}
static int self_test(void) {
 unsigned int a[]={SNDRV_CTL_TLVT_DB_SCALE,8,(unsigned)-7400,100};
 unsigned int b[]={SNDRV_CTL_TLVT_DB_SCALE,8,(unsigned)-9000,100};
 if(scale_value(0,74,a,4,-1200)!=62 || scale_value(0,74,a,4,0)!=74 || scale_value(0,120,b,4,0)!=90) return 1;
 if(scale_value(0,74,a,4,100)!=LONG_MIN || scale_value(0,74,a,3,0)!=LONG_MIN) return 2;
 a[0]=SNDRV_CTL_TLVT_DB_LINEAR;if(scale_value(0,74,a,4,0)!=LONG_MIN)return 3;
 a[0]=SNDRV_CTL_TLVT_DB_SCALE;a[3]=0;if(scale_value(0,74,a,4,0)!=LONG_MIN)return 4;
 a[3]=100|0x10000;if(scale_value(0,74,a,4,-7400)!=LONG_MIN)return 5;
 puts("AUDIO_CONTROL_READONLY_SCALE_TEST_PASS");return 0;
}
static int codec_matches(int card) {
 char path[128],line[256];int codec=0,subsystem=0;
 snprintf(path,sizeof(path),"/proc/asound/card%d/codec#0",card);
 FILE *fp=fopen(path,"r");if(!fp)return 0;
 while(fgets(line,sizeof(line),fp)) {
  if(strstr(line,"Vendor Id: 0x14f11f87"))codec=1;
  if(strstr(line,"Subsystem Id: 0x17aa3841"))subsystem=1;
 }
 fclose(fp);return codec&&subsystem;
}
int main(int argc,char **argv) {
 if(argc==2 && !strcmp(argv[1],"--self-test"))return self_test();
 if(argc!=3 || (strcmp(argv[1],"--dump") && strcmp(argv[1],"--speaker-xml")))return 64;
 char *end=NULL;errno=0;long c=strtol(argv[2],&end,10);
 if(errno || end==argv[2] || *end || c<0 || c>31)return 64;
 int xml=!strcmp(argv[1],"--speaker-xml");char path[128];
 if(!codec_matches((int)c)){fprintf(stderr,"Not the validated SN6140/17aa3841 codec; no configuration emitted\n");return 65;}
 snprintf(path,sizeof(path),"/dev/snd/controlC%ld",c);
 int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0){perror(path);return 66;}
 struct snd_ctl_card_info card={0};
 if(ioctl(fd,SNDRV_CTL_IOCTL_CARD_INFO,&card)<0 || strcmp((char *)card.id,"sofhdadsp")){close(fd);return 65;}
 struct snd_ctl_elem_list list={0};
 if(ioctl(fd,SNDRV_CTL_IOCTL_ELEM_LIST,&list)<0 || list.count>1024){close(fd);return 67;}
 struct snd_ctl_elem_id *ids=calloc(list.count?list.count:1,sizeof(*ids));
 if(!ids){close(fd);return 68;}
 list.space=list.count;list.pids=ids;
 if(ioctl(fd,SNDRV_CTL_IOCTL_ELEM_LIST,&list)<0){free(ids);close(fd);return 67;}
 for(unsigned int i=0;i<list.used;i++) {
  struct snd_ctl_elem_info info={0};info.id=ids[i];
  if(ioctl(fd,SNDRV_CTL_IOCTL_ELEM_INFO,&info)<0)continue;
  const char *name=(char *)info.id.name;
  int target=!strcmp(name,"Master Playback Volume") || !strcmp(name,"Speaker Playback Volume") || !strcmp(name,"Pre Mixer Analog Playback Volume") || !strcmp(name,"Post Mixer Analog Playback Volume");
  if(xml && (!target || info.id.index || info.id.iface!=SNDRV_CTL_ELEM_IFACE_MIXER || info.type!=SNDRV_CTL_ELEM_TYPE_INTEGER || !(info.access&SNDRV_CTL_ELEM_ACCESS_WRITE)))continue;
  unsigned int raw[258]={0};struct snd_ctl_tlv *t=(struct snd_ctl_tlv *)raw;t->numid=info.id.numid;t->length=1024;
  int got=ioctl(fd,SNDRV_CTL_IOCTL_TLV_READ,t)>=0;
  if(xml) {
   long cap=!strcmp(name,"Speaker Playback Volume")?-1200:0;
   long value=got?scale_value(info.value.integer.min,info.value.integer.max,t->tlv,256,cap):LONG_MIN;
   if(value==LONG_MIN){fprintf(stderr,"No supported dB scale: %s; original setting retained\n",name);continue;}
   printf("        <ctl name=\"%s\" value=\"%ld\" />\n",name,value);
   fprintf(stderr,"Speaker route: %s -> %ld (at/below %ld hundredths dB)\n",name,value,cap);
  } else {
   struct snd_ctl_elem_value value={0};value.id=ids[i];int ok=ioctl(fd,SNDRV_CTL_IOCTL_ELEM_READ,&value)>=0;
   printf("%u %s type=%u count=%u",info.id.numid,name,info.type,info.count);
   if(info.type==SNDRV_CTL_ELEM_TYPE_INTEGER || info.type==SNDRV_CTL_ELEM_TYPE_BOOLEAN) {
    printf(" range=%ld..%ld values=",info.value.integer.min,info.value.integer.max);
    for(unsigned int j=0;ok && j<info.count && j<8;j++)printf("%s%ld",j?",":"",value.value.integer.value[j]);
   } else if(info.type==SNDRV_CTL_ELEM_TYPE_ENUMERATED && ok)printf(" selected=%u",value.value.enumerated.item[0]);
   if(got && t->tlv[0]==SNDRV_CTL_TLVT_DB_SCALE && t->tlv[1]==8)printf(" dBmin=%d dBstep=%u mute_min=%u",(int)t->tlv[2],t->tlv[3]&0xffff,!!(t->tlv[3]&0x10000));
   puts("");
  }
 }
 free(ids);close(fd);return 0;
}
