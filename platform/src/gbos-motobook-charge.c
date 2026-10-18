// SPDX-License-Identifier: GPL-2.0-only
/* Charge-only VPC2004 interface for MOTOROLA 83NY. Uses the documented Linux
 * ideapad-laptop GBMD bit5 / SBMC 3,5 protocol. No keyboard, rfkill, fan, camera,
 * performance-profile or raw EC access; probing never changes charging mode. */
#include <linux/module.h>
#include <linux/acpi.h>
#include <linux/dmi.h>
#include <linux/device.h>
#include <linux/mutex.h>
static DEFINE_MUTEX(charge_lock);
static int get_mode(struct device *dev,bool *enabled)
{
 struct acpi_device *adev=dev_get_drvdata(dev);
 unsigned long long value;
 if(ACPI_FAILURE(acpi_evaluate_integer(adev->handle,"GBMD",NULL,&value)))return -EIO;
 *enabled=!!(value&BIT_ULL(5));return 0;
}
static ssize_t conservation_mode_show(struct device *dev,struct device_attribute *attr,char *buf)
{
 bool enabled;int ret;
 mutex_lock(&charge_lock);ret=get_mode(dev,&enabled);mutex_unlock(&charge_lock);
 return ret?ret:sysfs_emit(buf,"%u\n",enabled);
}
static ssize_t conservation_mode_store(struct device *dev,struct device_attribute *attr,const char *buf,size_t count)
{
 struct acpi_device *adev=dev_get_drvdata(dev);bool requested,old,actual;int ret;
 if(kstrtobool(buf,&requested))return -EINVAL;
 mutex_lock(&charge_lock);ret=get_mode(dev,&old);
 if(!ret&&requested!=old){
  if(ACPI_FAILURE(acpi_execute_simple_method(adev->handle,"SBMC",requested?3:5)))ret=-EIO;
  else{ret=get_mode(dev,&actual);if(!ret&&actual!=requested)ret=-EIO;}
 }
 mutex_unlock(&charge_lock);return ret?ret:count;
}
static DEVICE_ATTR_RW(conservation_mode);
static struct attribute *charge_attrs[]={&dev_attr_conservation_mode.attr,NULL};
static const struct attribute_group charge_group={.attrs=charge_attrs};
static int charge_add(struct acpi_device *adev)
{
 bool enabled;int ret;
 if(!dmi_match(DMI_SYS_VENDOR,"MOTOROLA")||!dmi_match(DMI_PRODUCT_NAME,"83NY"))return -ENODEV;
 if(!acpi_has_method(adev->handle,"GBMD")||!acpi_has_method(adev->handle,"SBMC"))return -ENODEV;
 dev_set_drvdata(&adev->dev,adev);ret=get_mode(&adev->dev,&enabled);if(ret)return ret;
 ret=sysfs_create_group(&adev->dev.kobj,&charge_group);
 if(!ret)dev_info(&adev->dev,"GBOS charge-only conservation interface ready; existing mode=%u unchanged\n",enabled);
 return ret;
}
static void charge_remove(struct acpi_device *adev){sysfs_remove_group(&adev->dev.kobj,&charge_group);}
static const struct acpi_device_id charge_ids[]={{"VPC2004",0},{}};
MODULE_DEVICE_TABLE(acpi,charge_ids);
static struct acpi_driver charge_driver={.name="gbos_motobook_charge",.class="battery",.ids=charge_ids,.ops={.add=charge_add,.remove=charge_remove}};
module_acpi_driver(charge_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("MOTOROLA 83NY charge-only ACPI conservation control");
