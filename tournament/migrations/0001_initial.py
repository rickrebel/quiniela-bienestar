import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Stadium',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('city', models.CharField(max_length=100, unique=True)),
                ('country', models.CharField(choices=[('us', 'Estados Unidos'), ('ca', 'Canadá'), ('mx', 'México')], max_length=2)),
                ('utc_offset', models.SmallIntegerField(help_text='Offset UTC del estadio durante el torneo (p. ej. -6).')),
                ('capacity', models.PositiveIntegerField(blank=True, null=True)),
                ('coords', models.CharField(blank=True, help_text='Coordenadas crudas de OF, en grados (string).', max_length=50)),
            ],
            options={
                'verbose_name': 'estadio',
                'verbose_name_plural': 'estadios',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Stage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('GROUP_STAGE', 'Fase de grupos'), ('LAST_32', 'Dieciseisavos de final'), ('LAST_16', 'Octavos de final'), ('QUARTER_FINALS', 'Cuartos de final'), ('SEMI_FINALS', 'Semifinales'), ('FINAL', 'Finales')], max_length=20, unique=True)),
                ('name', models.CharField(max_length=50)),
                ('short_name', models.CharField(max_length=20)),
                ('color', models.CharField(blank=True, help_text='Color hex, p. ej. #4CAF50.', max_length=7)),
                ('order', models.PositiveSmallIntegerField(unique=True)),
                ('opens_at', models.DateTimeField(blank=True, help_text='Apertura de predicciones (UTC). Antes: inputs off.', null=True)),
                ('confirm_deadline', models.DateTimeField(blank=True, help_text='Límite para confirmar (UTC). Al vencer: auto-confirma.', null=True)),
            ],
            options={
                'verbose_name': 'fase',
                'verbose_name_plural': 'fases',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('name_es', models.CharField(help_text='Nombre corto para mostrar, en español.', max_length=100)),
                ('fifa_code', models.CharField(max_length=3, unique=True)),
                ('flag_icon', models.CharField(blank=True, help_text='Bandera como emoji.', max_length=16)),
                ('flag_unicode', models.CharField(blank=True, max_length=120)),
                ('group_name', models.CharField(choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), ('F', 'F'), ('G', 'G'), ('H', 'H'), ('I', 'I'), ('J', 'J'), ('K', 'K'), ('L', 'L')], max_length=1)),
                ('confederation', models.CharField(choices=[('UEFA', 'UEFA'), ('CONMEBOL', 'CONMEBOL'), ('CONCACAF', 'CONCACAF'), ('CAF', 'CAF'), ('AFC', 'AFC'), ('OFC', 'OFC')], max_length=10)),
                ('fd_id', models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ('short_name', models.CharField(blank=True, max_length=50)),
                ('crest', models.URLField(blank=True, help_text='URL del escudo (FD).')),
                ('raw_of', models.JSONField(blank=True, default=dict)),
                ('raw_fd', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'verbose_name': 'selección',
                'verbose_name_plural': 'selecciones',
                'ordering': ['group_name', 'name_es'],
            },
        ),
        migrations.CreateModel(
            name='Match',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField(help_text='Fecha y hora del partido en UTC.')),
                ('home_placeholder', models.CharField(blank=True, help_text='Origen textual del equipo local (p. ej. "2A", "W74").', max_length=20)),
                ('away_placeholder', models.CharField(blank=True, max_length=20)),
                ('home_goals', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('away_goals', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('decided_by', models.CharField(blank=True, choices=[('REGULAR', 'Tiempo regular'), ('EXTRA_TIME', 'Tiempo extra'), ('PENALTY_SHOOTOUT', 'Penales')], max_length=20)),
                ('home_penalties', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('away_penalties', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('home_yellow', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('away_yellow', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('home_red', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('away_red', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('SCHEDULED', 'Programado'), ('TIMED', 'Con hora'), ('IN_PLAY', 'En juego'), ('PAUSED', 'Pausado'), ('FINISHED', 'Finalizado'), ('SUSPENDED', 'Suspendido'), ('POSTPONED', 'Pospuesto'), ('CANCELLED', 'Cancelado'), ('AWARDED', 'Adjudicado')], default='SCHEDULED', max_length=20)),
                ('of_number', models.PositiveSmallIntegerField(help_text='Número de partido 1..104 (73..104 = OF num).', unique=True)),
                ('fd_id', models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ('raw_fd', models.JSONField(blank=True, default=dict)),
                ('stadium', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='matches', to='tournament.stadium')),
                ('stage', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='matches', to='tournament.stage')),
                ('away_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='away_matches', to='tournament.team')),
                ('home_team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='home_matches', to='tournament.team')),
            ],
            options={
                'verbose_name': 'partido',
                'verbose_name_plural': 'partidos',
                'ordering': ['of_number'],
            },
        ),
    ]
