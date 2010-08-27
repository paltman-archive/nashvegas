from datetime import datetime

from django.db import models


class Migration(models.Model):
    
    migration_label = models.CharField(max_length=200)
    date_created = models.DateTimeField(default=datetime.now)
    content = models.TextField()
    scm_version = models.CharField(max_length=50, null=True, blank=True)
