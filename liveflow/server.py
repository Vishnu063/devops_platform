#!/usr/bin/env python3
"""LiveFlow: read-only, loopback-only Docker/Kubernetes/Jenkins topology viewer."""
import argparse
import base64
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
from threading import Lock
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import os

ROOT = Path(__file__).resolve().parent
MAX_RESOURCES = 60

def run(command, timeout=6):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(type(e).__name__ + ': ' + str(e)[:180]) from e
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr.strip() or 'Command failed')[:180])
    return proc.stdout


def node(nid, title, kind, source, status='unknown', detail=''):
    return {'id': nid, 'title': title[:90], 'kind': kind,
            'source': source, 'status': status, 'detail': detail[:220]}


def docker_resources():
    rows = run(['docker', 'ps', '-a', '--format', '{{json .}}'], timeout=8).splitlines()
    nodes, edges = {}, []
    for row in rows[:MAX_RESOURCES]:
        data = json.loads(row)
        cid = data.get('ID', '')
        if not cid: continue
        name = str(data.get('Names') or cid[:12])
        state = str(data.get('State', 'unknown')).lower()
        status = 'healthy' if state == 'running' else 'error' if state in ('dead', 'exited', 'restarting') else 'warning'
        ident = 'docker:container:' + cid
        image_id = 'docker:image:' + str(data.get('Image', 'unknown'))
        nodes[ident] = node(ident, name, 'Container', 'docker', status, str(data.get('Status', '')))
        nodes[image_id] = node(image_id, str(data.get('Image', 'image')), 'Image', 'docker', 'neutral')
        edges.append({'from': image_id, 'to': ident, 'label': 'runs'})
        for network in str(data.get('Networks') or '').split(','):
            network = network.strip()
            if not network: continue
            network_id = 'docker:network:' + network
            nodes[network_id] = node(network_id, network, 'Network', 'docker', 'neutral')
            edges.append({'from': ident, 'to': network_id, 'label': 'attached'})
    if len(rows) > MAX_RESOURCES:
        warning = f'Docker view truncated to first {MAX_RESOURCES} containers'
    else: warning = None
    return list(nodes.values()), edges, warning


def labels_match(selector, labels):
    if not selector: return False
    if any(labels.get(k) != v for k,v in selector.get('matchLabels', {}).items()): return False
    for rule in selector.get('matchExpressions', []):
        k, op, values = rule.get('key'), rule.get('operator'), rule.get('values', [])
        present, value = k in labels, labels.get(k)
        if op == 'In' and (not present or value not in values): return False
        if op == 'NotIn' and (present and value in values): return False
        if op == 'Exists' and not present: return False
        if op == 'DoesNotExist' and present: return False
        if op not in ('In','NotIn','Exists','DoesNotExist'): return False
    return True


def kube_resources(context, namespace):
    cmd = ['kubectl', '--context', context, '--namespace', namespace,
           '--request-timeout=5s', 'get', 'deployments,services,pods', '-o', 'json']
    result = json.loads(run(cmd, timeout=9))
    if not isinstance(result.get('items'), list): raise RuntimeError('Unexpected Kubernetes response')
    items = result['items']
    n, e = {}, []
    pods = [x for x in items if x.get('kind') == 'Pod'][:MAX_RESOURCES]
    deployments = [x for x in items if x.get('kind') == 'Deployment'][:MAX_RESOURCES]
    services = [x for x in items if x.get('kind') == 'Service'][:MAX_RESOURCES]
    for pod in pods:
        meta = pod.get('metadata') or {}; name = meta.get('name', '')
        phase = (pod.get('status') or {}).get('phase', 'Unknown')
        conds = (pod.get('status') or {}).get('conditions') or []
        ready = any(x.get('type') == 'Ready' and x.get('status') == 'True' for x in conds)
        status = 'healthy' if ready else 'error' if phase == 'Failed' else 'warning'
        key = f'k8s:pod:{meta.get("uid") or name}'
        n[key] = node(key, name, 'Pod', 'kubernetes', status, f'Phase {phase}; Ready {ready}')
    for deploy in deployments:
        meta = deploy.get('metadata') or {}; name = meta.get('name', '')
        key = f'k8s:deployment:{meta.get("uid") or name}'
        spec = deploy.get('spec') or {}; state = deploy.get('status') or {}
        wanted, available = spec.get('replicas',1), state.get('availableReplicas',0)
        status = 'healthy' if wanted == available else 'warning'
        n[key] = node(key, name, 'Deployment', 'kubernetes', status, f'{available}/{wanted} replicas available')
        selector = spec.get('selector') or {}
        for pod in pods:
            if labels_match(selector, (pod.get('metadata') or {}).get('labels') or {}):
                pid = f'k8s:pod:{(pod.get("metadata") or {}).get("uid") or (pod.get("metadata") or {}).get("name")}'
                if pid in n: e.append({'from':key, 'to':pid, 'label':'selector match'})
    for svc in services:
        meta = svc.get('metadata') or {}; name = meta.get('name', '')
        if name == 'kubernetes' and svc.get('spec',{}).get('type') == 'ClusterIP': continue
        key = f'k8s:service:{meta.get("uid") or name}'
        spec = svc.get('spec') or {}
        n[key] = node(key, name, 'Service', 'kubernetes', 'neutral', str(spec.get('type','ClusterIP')))
        selector = spec.get('selector') or {}
        for pod in pods:
            if selector and all(((pod.get('metadata') or {}).get('labels') or {}).get(k) == v for k,v in selector.items()):
                pid = f'k8s:pod:{(pod.get("metadata") or {}).get("uid") or (pod.get("metadata") or {}).get("name")}'
                if pid in n: e.append({'from':key, 'to':pid, 'label':'selector match'})
    truncated = len(items) > len(pods)+len(services)+len(deployments)
    return list(n.values()), e, 'Kubernetes view may be truncated (limit per resource kind)' if truncated else None


def jenkins_resources(url, job):
    # Only configured by CLI user, not a request parameter. Jenkins API token never goes to browser.
    url = url.rstrip('/')
    segments = [segment for segment in job.split('/') if segment]
    path = '/'.join('job/' + quote(segment,safe='') for segment in segments)
    if not path: raise RuntimeError('Jenkins job name required')
    build = url + '/' + path + '/lastBuild/'
    user, token = os.getenv('LIVEFLOW_JENKINS_USER'), os.getenv('LIVEFLOW_JENKINS_TOKEN')
    headers={'Accept':'application/json', 'User-Agent':'DevOps-LiveFlow/0.1'}
    if user and token:
        credentials = base64.b64encode(f'{user}:{token}'.encode()).decode()
        headers['Authorization'] = 'Basic ' + credentials
    def get(path):
        req=Request(build + path, headers=headers)
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read(524288))
    info=get('api/json?tree=number,result,building')
    stages=[]; warning=None
    try:
        timeline=get('wfapi/describe')
        stages=timeline.get('stages',[])[:MAX_RESOURCES]
    except Exception:
        warning='Jenkins stages unavailable; install Pipeline: REST API plugin (wfapi) or check permissions'
    nodes, edges = [], []
    status = 'warning' if info.get('building') else 'healthy' if info.get('result')=='SUCCESS' else 'error' if info.get('result') in ('FAILURE','ABORTED','UNSTABLE') else 'unknown'
    ident=f'jenkins:build:{job}'
    nodes.append(node(ident, job, 'Pipeline', 'jenkins', status, 'Build #' + str(info.get('number','?')) + ' ' + str(info.get('result') or 'running')))
    previous=ident
    for index, stage in enumerate(stages):
        state=stage.get('status','UNKNOWN').upper()
        stage_status = 'healthy' if state=='SUCCESS' else 'error' if state in ('FAILED','ABORTED') else 'warning' if state in ('IN_PROGRESS','PAUSED_PENDING_INPUT','UNSTABLE') else 'neutral'
        stage_id=f'jenkins:stage:{job}:{index}:{stage.get("name", "stage")}'
        nodes.append(node(stage_id, str(stage.get('name') or f'Stage {index+1}'), 'Stage', 'jenkins', stage_status, state))
        edges.append({'from':previous,'to':stage_id,'label':'next stage'})
        previous=stage_id
    return nodes, edges, warning



def optional_cluster_sources(args):
    """Fixed read-only commands. Absence/failure is a labelled disconnected source."""
    nodes=[];edges=[]
    if not args.context:return nodes,edges,'Kubernetes disconnected: explicit context not configured'
    base=['kubectl','--context',args.context,'--namespace',args.namespace,'--request-timeout=5s']
    events=json.loads(run([*base,'get','events','-o','json'],timeout=8))
    for item in events.get('items',[])[:MAX_RESOURCES]:
        meta=item.get('metadata',{});reason=item.get('reason','unknown')
        nodes.append(node('k8s:event:'+meta.get('uid',meta.get('name','unknown')),reason,'Event','kubernetes',
                          'warning' if item.get('type')=='Warning' else 'neutral',str(item.get('message',''))[:200]))
    return nodes,edges,None


def helm_resources(args):
    if not args.context:return [],[],'Helm disconnected: explicit Kubernetes context required'
    items=json.loads(run(['helm','--kube-context',args.context,'--namespace',args.namespace,'list','--output','json','--max','60'],timeout=8))
    return [node('helm:'+str(i.get('name')),str(i.get('name')),'Helm release','helm','healthy' if i.get('status')=='deployed' else 'warning',str(i.get('chart'))) for i in items[:MAX_RESOURCES]],[],None


def argocd_resources(args):
    if not args.context:return [],[],'Argo CD disconnected: explicit Kubernetes context required'
    items=json.loads(run(['kubectl','--context',args.context,'--namespace',args.argocd_namespace,'--request-timeout=5s','get','applications.argoproj.io','-o','json'],timeout=8))
    result=[]
    for i in items.get('items',[])[:MAX_RESOURCES]:
        status=i.get('status',{});health=status.get('health',{}).get('status','Unknown');sync=status.get('sync',{}).get('status','Unknown')
        name=i.get('metadata',{}).get('name','unknown')
        result.append(node('argocd:'+name,name,'Argo application','argocd','healthy' if health=='Healthy' and sync=='Synced' else 'warning',health+' / '+sync))
    return result,[],None


def incident_resources(args):
    if not args.ops_pilot_url:return [],[],'Ops Pilot disconnected: optional URL not configured'
    # Shared versioned transport is optional; standalone dashboard needs no package.
    from triage.ecosystem import endpoint,transport
    url=endpoint(args.ops_pilot_url)+'/integration/state'
    data=transport(url,os.environ.get('OPS_PILOT_READ_TOKEN',''),retries=0)
    return [node('incident:'+i['id'],i['service'],'Incident','ops-pilot','healthy' if i['status']=='verified' else 'warning',i['status']) for i in data.get('incidents',[])[:MAX_RESOURCES]],[],None


class Collector:
    def __init__(self, args):
        self.args=args
        self.lock=Lock()
        self.previous={}
        self.events=deque(maxlen=60)
        self.started=set()
    def snapshot(self):
        with self.lock:
            groups={}
            configs={'docker': lambda:docker_resources()}
            if self.args.context:
                configs['kubernetes']=lambda:kube_resources(self.args.context,self.args.namespace)
            if self.args.jenkins_url and self.args.jenkins_job:
                configs['jenkins']=lambda:jenkins_resources(self.args.jenkins_url,self.args.jenkins_job)
            if getattr(self.args,'cluster_events',False):configs['cluster-events']=lambda:optional_cluster_sources(self.args)
            if getattr(self.args,'helm',False):configs['helm']=lambda:helm_resources(self.args)
            if getattr(self.args,'argocd_namespace',None):configs['argocd']=lambda:argocd_resources(self.args)
            if getattr(self.args,'ops_pilot_url',None):configs['ops-pilot']=lambda:incident_resources(self.args)
            source_state={}
            now=datetime.now(timezone.utc).isoformat(timespec='seconds')
            for source, fetch in configs.items():
                try:
                    new_nodes, edges, warning=fetch()
                    new={n['id']:n for n in new_nodes}
                    old=self.previous.get(source,{})
                    if source in self.started:
                        for key in sorted(new.keys()-old.keys()):
                            self.events.appendleft({'at':now,'action':'created','source':source,'name':new[key]['title'],'kind':new[key]['kind']})
                        for key in sorted(old.keys()-new.keys()):
                            self.events.appendleft({'at':now,'action':'deleted','source':source,'name':old[key]['title'],'kind':old[key]['kind']})
                        for key in sorted(new.keys() & old.keys()):
                            if (new[key]['status'],new[key]['detail']) != (old[key]['status'],old[key]['detail']):
                                self.events.appendleft({'at':now,'action':'changed','source':source,'name':new[key]['title'],'kind':new[key]['kind']})
                    self.started.add(source)
                    self.previous[source]=new
                    groups[source]={'nodes':new_nodes,'edges':edges}
                    source_state[source]={'ok':True,'warning':warning}
                except Exception as ex:
                    # Retain old nodes; failed API calls are not proof resources were deleted.
                    groups[source]={'nodes':[dict(n,status='unknown') for n in self.previous.get(source,{}).values()], 'edges':[]}
                    source_state[source]={'ok':False,'warning':str(ex)[:200]}
            return {'at':now, 'groups':groups, 'sources':source_state, 'events':list(self.events), 'intervalSeconds':5,'security':{'status':'not configured','note':'No vulnerability scanner or log backend connected; absence is not a clean security finding'}}


def serve(args):
    collector=Collector(args)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route=urlparse(self.path).path
            if route=='/api/snapshot':
                try:
                    body=json.dumps(collector.snapshot(),separators=(',',':')).encode()
                    status=200; mime='application/json; charset=utf-8'
                except Exception:
                    body=b'{"error":"Collection failed"}';status=500;mime='application/json'
            elif route in ('/','/index.html'):
                body=(ROOT/'index.html').read_bytes();status=200;mime='text/html; charset=utf-8'
            else:
                body=b'Not found';status=404;mime='text/plain'
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def log_message(self,format,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'LiveFlow read-only dashboard: http://127.0.0.1:{args.port} (loopback only)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8769)
    parser.add_argument('--context',help='Explicit kubectl context to observe; omitted disables Kubernetes collection')
    parser.add_argument('--namespace',default='default',help='Kubernetes namespace to observe (default: default)')
    parser.add_argument('--jenkins-url',help='HTTPS URL, or loopback HTTP URL, for Jenkins')
    parser.add_argument('--jenkins-job',help='Jenkins job name, optionally folder/job')
    parser.add_argument('--cluster-events',action='store_true',help='Read-only namespaced Kubernetes events')
    parser.add_argument('--helm',action='store_true',help='Read-only Helm release status')
    parser.add_argument('--argocd-namespace',help='Read-only Argo Application CRs in this explicit namespace')
    parser.add_argument('--ops-pilot-url',help='Optional loopback HTTP or HTTPS base URL; read-only credential comes from OPS_PILOT_READ_TOKEN')
    args=parser.parse_args(argv)
    if not (1<=args.port<=65535): parser.error('port must be from 1 through 65535')
    if (args.jenkins_url is None) != (args.jenkins_job is None): parser.error('Provide both --jenkins-url and --jenkins-job')
    if args.jenkins_url:
        parsed=urlparse(args.jenkins_url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme != 'https' and not(parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1'))):
            parser.error('Jenkins must use HTTPS, or HTTP on localhost; no credentials embedded in URL')
    serve(args)

if __name__=='__main__': main()

