from datetime import datetime as dt

from fabfile.config import *
from fabfile.utils.fabos import detect_ostype
from fabfile.utils.host import get_env_passwords, get_authserver_credentials
from fabric.contrib.files import exists

@roles('all')
@task
def tar_logs_cores():
    sudo("rm -f /var/log/logs_*.tgz")
    sudo("rm -f /var/crashes/*gz")
    sudo("rm -f /var/log/gdb*.log")
    sudo("rm -f /var/log/contrail*.log")
    sudo("rm -rf /var/log/temp_log")
    sudo("rm -rf /var/temp_log")
    a = dt.now().strftime("%Y_%m_%d_%H_%M_%S")
    d = env.host_string
    e=sudo('hostname')
    sudo ("mkdir -p /var/temp_log; cp -R /var/log/* /var/temp_log")
    sudo ("mv /var/temp_log /var/log/temp_log")
    sudo ("cd /var/log/temp_log/ ; tar czf /var/log/logs_%s_%s.tgz *"%(e, a))
    if not check_file_exists('/usr/bin/gdb'):
        install_pkg(['gdb'])
    core_folder = '/var/crashes'
    with settings(warn_only=True):
        if "core" in sudo("ls -lrt %s" % (core_folder)):
            output = sudo("ls -lrt %s" % (core_folder))
            core_list = output.split('\n')
            for corename in core_list:
                if "core" in corename:
                    core = corename.split()[8]
                    name = core.split('.')[1]
                    binary_name_cmd = 'strings %s/%s | grep "^/usr/bin/%s" | head -1' %(
                        core_folder, core, name)
                    rname = sudo(binary_name_cmd)
                    if check_file_exists(rname):
                        name = sudo("basename %s" %rname)
                    core_new = core.rstrip('\r')
                    sudo("gdb %s /var/crashes/%s --eval-command bt > /var/log/gdb_%s.log --eval-command quit"%(name, core_new, core_new))
            sudo ("mkdir -p /var/crashes/saved")
            sudo ("cp /var/crashes/core* /var/crashes/saved/")
            sudo ("gzip /var/crashes/core*")
            sudo ("cd /var/crashes; for i in core*.gz; do mv -f $i %s_$i; done" %(e) )
        sudo("contrail-version > /var/log/contrail_version_%s_%s.log"%(e,a))

#end tar_logs_cores

def check_file_exists(filepath):
    if exists(filepath):
        return True
    return False

def install_pkg(pkgs):
    ostype = detect_ostype()
    for pkg in pkgs:
        with settings(warn_only = True):
            if ostype in ['fedora', 'centos', 'redhat', 'centoslinux']:
                sudo("yum -y install %s" % (pkg))
            elif ostype in ['ubuntu']:
                sudo("DEBIAN_FRONTEND=noninteractive apt-get -y --force-yes install %s" %(pkg))


@roles('collector')
@task
def get_cassandra_logs(duration = None):
    if env.host_string != env.roledefs['collector'][0]:
        print 'No need to get cassandra logs on this host'
        return
    sudo("rm -f /var/log/cassandra_log_*")
    a = dt.now().strftime("%Y_%m_%d_%H_%M_%S")
    d = env.host_string
    e=sudo('hostname')
    if duration is None:
        output = sudo("cat /proc/uptime") 
        uptime_seconds = float(output.split()[0]) 
        uptime_min=uptime_seconds/60
        uptime_min=int(uptime_min) 
        uptime_min=str(uptime_min) + 'm'
        print "Node %s is up for %s. Collecting Cassandra logs for %s" %(e,uptime_min,uptime_min)
    else:
        uptime_min=str(duration) + 'm'
        print "Duration value is %s . Collecting Cassandra logs for %s" %(uptime_min,uptime_min)
    cmd = "/usr/bin/contrail-logs --last %s --all" %(uptime_min)
    admin_user, admin_password = get_authserver_credentials()
    cmd += " --admin-user %s --admin-password %s" % (admin_user, admin_password)
    with settings(warn_only=True):
        sudo("%s -o /var/log/cassandra_log_%s_%s.log" %(cmd,e,a))
        sudo("gzip /var/log/cassandra_log_*" )
        print "\nCassandra logs are saved in /var/log/cassandra_log_%s_%s.log.gz of %s" %( e, a , e )
#end get_cassandra_logs

@roles('database')
def get_cassandra_db_files():
    sudo("rm -rf /var/cassandra_log")
    a = dt.now().strftime("%Y_%m_%d_%H_%M_%S")
    d = env.host_string
    e = sudo('hostname')
    sudo("mkdir -p /var/cassandra_log")
    if exists('/home/cassandra/'):
        sudo("cp -R /home/cassandra/* /var/cassandra_log")
    elif exists('/var/lib/cassandra/'):
        sudo("cp -R /var/lib/cassandra/* /var/cassandra_log")
    else:
        print "cassandra directory not available in standard location..."
    sudo("cd /var/cassandra_log; tar -czf cassandra_file_%s_%s.tgz *" %(e,a))
    print "\nCassandra DB files are saved in /var/cassandra_log/cassandra_file_%s_%s.tgz of %s" %( e,a ,e)
#end get_cassandra_db_file

@roles('build')
@task
def attach_logs_cores(bug_id, timestamp=None, duration=None, analytics_log='yes'):
    '''
    Attach the logs, core-files, bt and contrail-version to a specified location
    
    If argument duration is specified it will collect the cassandra logs for specifed
    duration. Unit of the argument duration is minute. If not specifed it will collect
    cassandra log for system uptime
    '''
    build= env.roledefs['build'][0]
    if timestamp:
        folder= '%s/%s' %( bug_id, timestamp) 
    else:
        time_str = dt.now().strftime("%Y_%m_%d_%H_%M_%S")
        folder='%s/%s' %(bug_id, time_str)
    local('mkdir -p %s' % ( folder ) )
    execute(tar_logs_cores)
    if analytics_log == 'yes':
        execute(get_cassandra_logs,duration)
    with hide('everything'):
        for host in env.roledefs['all']:
            with settings( host_string=host, password=get_env_passwords(host),
                           connection_attempts=3, timeout=20, warn_only=True):
                get('/var/log/logs_*.tgz', '%s/' %( folder ) )
                get('/var/crashes/*gz', '%s/' %( folder ) )
                get('/var/log/gdb_*.log','%s/' %( folder ) )
                get('/var/log/contrail_version*.log','%s/' %( folder ) )
                if analytics_log is 'yes':
                    get('/var/log/cassandra_log*.gz','%s/' %( folder ) )

    print "\nAll logs and cores are saved in %s of %s" %(folder, env.host) 
#end attach_logs_cores
