from django.db import models

class login_data(models.Model):
    empid = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    password = models.CharField(max_length=128, default='1234')
