from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pool', '0011_remove_stageuser_stage_remove_stageuser_user_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='userquiniela',
            name='history_compare',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='IDs de usuario comparados en la gráfica Historia, '
                          'en orden de selección. null = sin personalizar.',
            ),
        ),
    ]
