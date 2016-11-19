import os, requests, time, json, smtplib, subprocess

API = "https://api.digitalocean.com/v2/droplets"
HEADERS = {
    "Authorization": "Bearer %s" %os.environ['TOKEN'],
    "Content-Type": "application/json"
}
DROPLET_NAME = "ol-tester"
TEST_SCRIPT = "test.sh"
TEST_OUTPUT = ""
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def post(args):
    r = requests.post(API, data=args, headers=HEADERS)
    return r.json()

def get(args):
    r = requests.get(API, data=args, headers=HEADERS)
    return r.json()

def start():
    r = requests.get("https://api.digitalocean.com/v2/account/keys", headers=HEADERS)
    keys = map(lambda row: row['id'], r.json()['ssh_keys'])

    args = {
        "name":DROPLET_NAME,
        "region":"nyc2",
        "size":"512mb",
        "image":"ubuntu-14-04-x64",
        "ssh_keys":keys
    }
    r = requests.post(API, data=json.dumps(args), headers=HEADERS)
    return r.json()

def lookup(droplet_id):
    r = requests.get('%s/%s' % (API, droplet_id), headers=HEADERS)
    return r.json()['droplet']

def kill():
    global TEST_OUTPUT
    args = {}
    droplets = get(args)['droplets']
    for d in droplets:
        if d['name'] == DROPLET_NAME:
            TEST_OUTPUT += 'Deleting %s (%d)\n' % (d['name'], d['id'])
            TEST_OUTPUT += '%s\n' % requests.delete('%s/%s' % (API, d['id']), headers=HEADERS)

def test():
    global TEST_OUTPUT
    # cleanup just in case
    kill()

    # create new droplet and wait for it
    droplet = start()['droplet']

    while True:
        droplet = lookup(droplet['id'])

        # status
        s = droplet['status']
        try:
            assert(s in ['active', 'new'])
        except:
            TEST_OUTPUT += 'Droplet %s (%d) status not active or new. Giving up.'
            return False

        # addr
        ip = None
        for addr in droplet["networks"]["v4"]:
            if addr["type"] == "public":
                ip = addr["ip_address"]
        
        TEST_OUTPUT += 'STATUS: %s, IP: %s\n' % (str(s), str(ip))
        if s == 'active' and ip != None:
            break

        time.sleep(3)

    time.sleep(30) # give SSH some time

    script_path = os.path.join(SCRIPT_DIR, TEST_SCRIPT)
    scp = ['/usr/bin/scp', '-o', '"StrictHostKeyChecking no"', script_path, 'root@%s:/tmp' % ip]
    TEST_OUTPUT += 'RUN %s\n' % ' '.join(scp)
    try:
        TEST_OUTPUT += subprocess.check_output(scp)
    except subprocess.CalledProcessError as e:
        TEST_OUTPUT += str(e.output)
        TEST_OUTPUT += 'SCP with code %s failed. Giving up.\n' % str(e.returncode)
        return False

    cmds = 'bash /tmp/%s' % TEST_SCRIPT
    ssh = ['/usr/bin/echo', cmds, '|', '/usr/bin/ssh', '-o', '"StrictHostKeyChecking no"', 'root@%s' % ip]
    TEST_OUTPUT += 'RUN %s\n' % ' '.join(ssh)
    try:
        TEST_OUTPUT += subprocess.check_output(ssh)
    except subprocess.CalledProcessError as e:
        TEST_OUTPUT += str(e.output)
        TEST_OUTPUT += 'SCP with code %s failed. Giving up.\n' % str(e.returncode)
        return False

    # make sure we cleanup everything!
    kill()

    return True

def scold(commit):
    user = os.environ['EMAIL']
    pw = os.environ['PW']

    FROM = user
    #TO = [commit['committer']['email'], 'tyler.harter@gmail.com', 'ed.nmi.oakes@gmail.com']
    TO = [commit['committer']['email'], 'ed.nmi.oakes@gmail.com']
    SUBJECT = 'OpenLambda Broken Commit %s' % commit['id']
    TEXT = """Your latest commit (sha: %s, message: '%s') failed the automated tests. Please push (or roll back to) a working commit as soon as possible.\n\n\
            If you are unable to fix this or think there's an issue with the tests, please contact Ed Oakes (ed.nmi.oakes@gmail.com) or Tyler Harter (tyler.harter@gmail.com) so we can address the issue.\n\n\
            Here is the output of the tests for reference:\n\n%s\n\n\
            <----------------- DO NOT REPLY TO THIS EMAIL ADDRESS ----------------->""" % (commit['id'], commit['message'], TEST_OUTPUT)
    message = """From: %s\nTo: %s\nSubject:%s\n\n%s
              """ % (FROM, ', '.join(TO), SUBJECT, TEXT)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(user, pw)
        server.sendmail(FROM, TO, message)
        server.close()
        return 'tests failed and successfully sent the email'
    except Exception as e:
        return 'tests failed but couldn\'t send the email: %s' % e

# aws entry
def lambda_handler(event, context):
    if not test():
        return scold(event['head_commit'])

    return 'Tests passed'
    
