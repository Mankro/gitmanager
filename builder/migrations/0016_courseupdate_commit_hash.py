# Generated by Django 3.2.15 on 2023-03-21 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('builder', '0015_course_skip_build_failsafes'),
    ]

    operations = [
        migrations.AddField(
            model_name='courseupdate',
            name='commit_hash',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
    ]
