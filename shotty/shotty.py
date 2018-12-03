import boto3
import click
import botocore

session = boto3.Session(profile_name='shotty')
ec2 = session.resource('ec2')


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

@click.group()
@click.option('--profile', default='shotty', help="Specify an alternate profile for AWS session")
def cli(profile):
    """Shotty manages snapshots"""
    session = boto3.Session(profile_name=profile)
    ec2 = session.resource('ec2')


@cli.group('snapshots')
def snapshots():
    """Commands for snapshots"""

@snapshots.command('list')
@click.option('--project', default=None, help="Only snapshots for project (tag Project:<name>)")
@click.option('--all', 'list_all', default=False, is_flag=True,
              help="List all snapshots for each volume, not just the most recent")
def list_snapshots(project, list_all):
    "List snapshots"
    instances = []
    
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
def list_volumes(project):
    "List volumes"
    instances = []

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
def create_snapshots(project, force_flag):
    "Create snapshots for EC2 instances"
    if not project and not force_flag:
        print("Cannot create snapshots unless project is specified or force is specified")
        return
    
    instances = []
    
    instances = filter_instances(project)

    for i in instances:
        print("Stopping {0}...".format(i.id))
        
        i.stop()
        i.wait_until_stopped()

        for v in i.volumes.all():
            if has_pending_snapshot(v):
                print("  Skipping {0}, snapshot already in progress.".format(v.id))
                continue
            print("  Creating snapshot of {0}".format(v.id))
            try:
                v.create_snapshot(Description="Created by SnapshotAlyzer 30000")
            except botocore.exceptions.ClientError:
                print("  Error generating snapshot for {0}, skipping. ".format(v.id) + str(e))
                continue

        print("Starting {0}...".format(i.id))
                
        i.start()
        i.wait_until_running()

    print("Job's done!")

    return

@instances.command('list')
@click.option('--project', default=None, help="Only instances for project (tag Project:<name>)")
def list_instances(project):
    "List instances"
    instances = []
    
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
def stop_instances(project, force_flag):
    "Stop EC2 instances"
    if not project and not force_flag:
        print("Cannot create snapshots unless project is specified or force is specified")
        return

    instances=[]

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
def start_instances(project, force_flag):
    "Start EC2 instances"
    if not project and not force_flag:
        print("Cannot create snapshots unless project is specified or force is specified")
        return
    
    instances=[]
    
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
def reboot_instances(project, force_flag):
    "Reboot EC2 instances"
    if not project and not force_flag:
        print("Cannot create snapshots unless project is specified or force is specified")
        return
    
    instances=[]
    
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
