from django.db import models
from django.utils import timezone


class Migration(models.Model):
    
    migration_label = models.CharField(max_length=200)
    date_created = models.DateTimeField(default=timezone.now)
    content = models.TextField()
    scm_version = models.CharField(max_length=50, null=True, blank=True)
    
    def __unicode__(self):
        return unicode("%s [%s]" % (self.migration_label, self.scm_version))
