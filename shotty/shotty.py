import boto3
import click
import botocore
from datetime import datetime, timezone

#session = boto3.Session(profile_name='shotty')
#ec2 = session.resource('ec2')
session = None
ec2 = None

def single_instance(instance_name):
    instances=[]
    filters = [{'Name':'instance-id', 'Values':[instance_name]}]
    instances=ec2.instances.filter(Filters=filters)

    return instances

def filter_instances(project):
    instances = []
        
    if project:
        filters = [{'Name':'tag:Project', 'Values':[project]}]
        instances = ec2.instances.filter(Filters=filters)
    else:
        instances= ec2.instances.all()

    return instances

def has_pending_snapshot(volume):
    snapshots = list(volume.snapshots.all())
    return snapshots and snapshots[0].state == 'pending'

def has_newer_snapshot(volume,age):
    today = datetime.now(timezone.utc)
    snaps = list(volume.snapshots.all())
    snap_age = today - snaps[0].start_time
    return snap_age.days < age

@click.group()
@click.option('--profile', default='shotty', help="Specify an alternate profile for AWS session")
@click.option('--region', default='', help="Specify an alternate region for AWS session")
def cli(profile, region):
    """Shotty manages snapshots"""
    global session, ec2

    print ("In cli, profile is {0} and region is {1}".format(profile,region))
    if region:
        session = boto3.Session(profile_name=profile,region_name=region)
        print ("Executed with region")
    else:
        session = boto3.Session(profile_name=profile)
    ec2 = session.resource('ec2')


@cli.group('snapshots')
def snapshots():
    """Commands for snapshots"""

@snapshots.command('list')
@click.option('--project', default=None, help="Only snapshots for project (tag Project:<name>)")
@click.option('--all', 'list_all', default=False, is_flag=True,
              help="List all snapshots for each volume, not just the most recent")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def list_snapshots(project, list_all, instance):
    "List snapshots"
    instances = []
    
    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)

    for i in instances:
        for v in i.volumes.all():
            for s in v.snapshots.all():
                print(", ".join((
                            s.id,
                            v.id,
                            i.id,
                            s.state,
                            s.progress,
                            s.start_time.strftime("%c")
                            )))
                if s.state == 'completed' and not list_all: break

    return

@cli.group('volumes')
def volumes():
    """Commands for volumes"""

@volumes.command('list')
@click.option('--project', default=None, help="Only volumes for project (tag Project:<name>)")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def list_volumes(project,instance):
    "List volumes"
    instances = []

    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)

    for i in instances:
        for v in i.volumes.all():
            print(", ".join((
                         v.id,
                         i.id,
                         v.state,
                         str(v.size) + "GiB",
                         v.encrypted and "Encrypted" or "Not Encrypted"
                         )))
    return

@cli.group('instances')
def instances():
    """Commands for instances"""

@instances.command('snapshot', help="Create snapshots of all volumes")
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force_flag', default=False, is_flag=True,
              help="Forces operation if project is not specified")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
@click.option('--age', default=0, help="Specify an 'older than' age for creating a new snapshot, in days")
def create_snapshots(project, force_flag,instance,age):
    "Create snapshots for EC2 instances"
    if not project and not instance and not force_flag:
        print("Cannot create snapshots unless project, instance or force is specified")
        return
    
    instances = []


    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)

    for i in instances:
        print("Checking {0}...".format(i.id))
        
        previous_state = i.state['Name']
       

        for v in i.volumes.all():
            if has_pending_snapshot(v):
                print("  Skipping {0}, snapshot already in progress.".format(v.id))
                continue
            if has_newer_snapshot(v,age):
                print("  Skipping {0}, already has a snapshot less than {1} days old.".format(v.id,age))
                continue
            if i.state['Name'] == 'running':
                print(" Stopping {0}...".format(i.id))
                i.stop()
                i.wait_until_stopped()
            print("  Creating snapshot of {0}".format(v.id))
            try:
                v.create_snapshot(Description="Created by SnapshotAlyzer 30000")
            except botocore.exceptions.ClientError as e:
                print("  Error generating snapshot for {0}, skipping. ".format(v.id) + str(e))
                continue

        
        if previous_state == 'running':
            print("Starting {0}...".format(i.id))
            i.start()
            i.wait_until_running()

    print("Job's done!")

    return

@instances.command('list')
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def list_instances(project,instance):
    "List instances"
    instances = []
    
    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)

    for i in instances:
        tags = { t['Key']: t['Value'] for t in i.tags or []}
        print(', '.join((
            i.id,
            i.instance_type,
            i.placement['AvailabilityZone'],
            i.state['Name'],
            i.public_dns_name,
            tags.get('Project', '<no project>'))))

    return

@instances.command('stop')
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force_flag', default=False, is_flag=True,
              help="Forces operation if project is not specified")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def stop_instances(project, force_flag,instance):
    "Stop EC2 instances"
    if not project and not instance and not force_flag:
        print("Cannot stop instances unless project, instance or force is specified")
        return

    instances=[]

    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)
    
    for i in instances:
        print("Stopping {0}...".format(i.id))
        try:
            i.stop()
        except botocore.exceptions.ClientError as e:
            print("  Could not stop {0}. ".format(i.id) + str(e))
            continue

    return

@instances.command('start')
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force_flag', default=False, is_flag=True,
              help="Forces operation if project is not specified")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def start_instances(project, force_flag,instance):
    "Start EC2 instances"
    if not project and not instance and not force_flag:
        print("Cannot start instances unless project, instance or force is specified")
        return

    instances=[]
    
    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)
    
    for i in instances:
        print("Starting {0}...".format(i.id))
        try:
            i.start()
        except botocore.exceptions.ClientError as e:
                print("  Could not start {0}. ".format(i.id) + str(e))
                continue
    
    return

@instances.command('reboot')
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force_flag', default=False, is_flag=True,
              help="Forces operation if project is not specified")
@click.option('--instance', default=None, help="Specify instance to operate on, overrides project flag")
def reboot_instances(project, force_flag,instance):
    "Reboot EC2 instances"
    if not project and not instance and not force_flag:
        print("Cannot reboot instances unless project, instance or force is specified")
        return

    instances=[]
    
    if instance:
        instances = single_instance(instance)
    else:
        instances = filter_instances(project)
    
    for i in instances:
        print("Rebooting {0}...".format(i.id))
        try:
            i.reboot()
        except botocore.exceptions.ClientError as e:
            print("  Could not reboot {0}. ".format(i.id) + str(e))
            continue

    return


if __name__ =='__main__':
    cli()
