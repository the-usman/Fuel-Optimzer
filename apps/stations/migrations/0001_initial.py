"""Initial schema for the Station table."""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Station',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('opis_id', models.PositiveIntegerField(unique=True)),
                ('name', models.CharField(max_length=255)),
                ('address', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=100)),
                ('state', models.CharField(db_index=True, max_length=2)),
                ('rack_id', models.PositiveIntegerField(blank=True, null=True)),
                ('retail_price', models.DecimalField(decimal_places=8, max_digits=12)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
            ],
            options={
                'ordering': ['opis_id'],
            },
        ),
    ]
