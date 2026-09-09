"""Read only YOKL's live catalog; write an isolated local ranking input snapshot."""
import json
from pathlib import Path
import ssl
import subprocess
import urllib.request
import certifi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ranking_yokl_20260909'


def main():
    secret = json.loads(subprocess.check_output(['aws', 'secretsmanager', 'get-secret-value',
        '--secret-id', 'aeo-admin/prod', '--profile', 'aeo-admin', '--region', 'us-east-1',
        '--query', 'SecretString', '--output', 'text'], text=True))
    def get(path, bearer=False):
        headers = {'Authorization': 'Bearer ' + secret['READ_API_TOKEN']} if bearer else {
            'X-Executor-Token': secret['EXECUTOR_TOKEN']}
        req = urllib.request.Request('https://jjm59vpn3y.us-east-1.awsapprunner.com' + path, headers=headers)
        with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context(cafile=certifi.where())) as r:
            return json.load(r)
    businesses = get('/api/businesses')
    biz = next(b for b in businesses if b['id'] == 363)
    assert biz['clientId'] == 329 and biz['name'] == 'Yokl, Inc.'
    client = get('/api/clients/329')
    keywords = get('/api/keywords?businessId=363&includeLocked=true')
    ids = sorted(k['id'] for k in keywords)
    assert ids == [5221, 5222, 5223, 5224, 5225]
    assert all(k['businessId'] == 363 and k['clientId'] == 329 and k['aeoPlanId'] == 502
               and k['isActive'] and not k.get('archivedAt') for k in keywords)
    address = biz['publishedAddress']
    assert address == '129 Cedar Avenue, Hershey, PA 17033'
    assert all(k['campaignName'].split('—', 1)[1].strip() == address for k in keywords)
    history = get('/api/ranking-reports?businessId=363&limit=1000', bearer=True)
    assert history['meta']['total'] == len(history['data']), 'Incomplete ranking history'
    OUT.mkdir(exist_ok=False)
    catalog = OUT / 'catalog'
    catalog.mkdir()
    for name, data in {'biz_admin.json':[biz], 'clients_admin.json':[client],
                       'kw_admin.json':keywords, 'rr_admin.json':history['data']}.items():
        (catalog/name).write_text(json.dumps(data, indent=2))
    (OUT/'keywords.json').write_text(json.dumps(ids))
    (OUT/'scope.json').write_text(json.dumps({'business_id':363,'client_id':329,
        'business_name':biz['name'], 'keyword_ids':ids, 'platforms':['chatgpt','gemini','copilot'],
        'maximum_pairs':15, 'address_source':'matching business publishedAddress and campaignName',
        'address':address, 'history_rows':len(history['data']), 'backend_writes':False}, indent=2))
    print(json.dumps({'business':biz['name'],'keyword_ids':ids,'pairs':15,'history_rows':len(history['data'])}))


if __name__ == '__main__':
    main()
