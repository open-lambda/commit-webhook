import os, requests, time, json, smtplib

API = "https://api.digitalocean.com/v2/droplets"
DROPLET_NAME = "ol-tester"
TEST_SCRIPT = "test.sh"
TEST_OUTPUT = ""
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__)

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
    TEST_OUTPUT += '%s\n' % droplet

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

    scp = 'scp -o "StrictHostKeyChecking no" %s root@%s:/tmp' % (TEST_SCRIPT, ip)
    TEST_OUTPUT += 'RUN %s\n' % scp
    rv = os.system(scp)
    try:
        assert(rv == 0)
    except:
        TEST_OUTPUT += 'SCP failed. Giving up.\n'
        return False

    cmds = 'bash /tmp/%s' % TEST_SCRIPT
    ssh = 'echo "<CMDS>" | ssh -o "StrictHostKeyChecking no" root@<IP>'
    ssh = ssh.replace('<CMDS>', cmds).replace('<IP>', ip)
    TEST_OUTPUT += 'RUN %s\n' % ssh
    rv = os.system(ssh)
    try:
        assert(rv == 0)
    except:
        TEST_OUTPUT += 'SSH command failed. Giving up.\n'
        return False

    # make sure we cleanup everything!
    kill()

    return True

def scold(commit):
    gmail_path = os.path.join(SCRIPT_DIR, 'gmail.txt')
    with open(gmail_path. 'r') as fd:
        user = fd.readline().strip()
        pw = fd.readline().strip()

    FROM = user
    TO = commit['author']['email']
    SUBJECT = 'OpenLambda Broken Commit %s' % commit['id']
    TEXT = 'Your latest commit (sha: %s) failed the automated tests. Please push (or roll back to) a working commit as soon as possible.\n\n
            If you are unable to fix this or think there\'s an issue with the tests, please contact Ed Oakes (ed.nmi.oakes@gmail.com) or Tyler Harter (tyler.harter@gmail.com) so we can address the issue.\n\n
            Here is the output of the tests for reference:\n\n%s\n\n
            <----------------- DO NOT REPLY TO THIS EMAIL ADDRESS ----------------->' % (commit['id'], TEST_OUTPUT)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(user, pw)
        server.sendmail(FROM, TO, message)
        server.close()
        return 'tests failed and successfully sent the email'
    except:
        return 'tests failed but couldn\'t send the email'

# aws entry
def lambda_handler(event, context):
    token_path = os.path.join(SCRIPT_DIR, 'token.txt')

    with open(token_path, 'r') as fd:
        token = fd.read().strip()

    global HEADERS
    HEADERS = {
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json"
    }

    if not test():
        return scold(event['head_commit'])

    return 'Tests passed'
