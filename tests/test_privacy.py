import io
import json
from studio.privacy import redact, public_error
from test_core import payload, wait, make_audio


def test_cross_site_reads_rejected(client):
    for path in ('/api/bootstrap','/api/history','/api/preferences'):
        assert client.get(path,headers={'Origin':'https://untrusted.example'}).status_code==403
        assert client.get(path,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403


def test_session_token_and_request_limit(client):
    assert client.post('/api/jobs',json=payload(),headers={'X-Studio-Token':'bad'}).status_code==403
    assert client.post('/api/preferences',content=b'x'*140000).status_code==413


def test_validation_does_not_echo_input(client):
    response=client.post('/api/jobs',json=payload(text='',confidential='DO-NOT-ECHO'))
    assert response.status_code==422 and 'DO-NOT-ECHO' not in response.text
    assert 'input' not in response.json()['detail'][0]


def test_diagnostics_do_not_contain_paths_or_prompts(client):
    wait(client,client.post('/api/jobs',json=payload(text='CONFIDENTIAL-TEXT')).json()['id'])
    text=client.get('/api/diagnostics').text
    assert 'CONFIDENTIAL-TEXT' not in text and 'executable' not in text and 'token' not in text
    assert 'torch' in text


def test_safe_metadata_export(client):
    job=wait(client,client.post('/api/jobs',json=payload(text='CONFIDENTIAL-TEXT',instruct='PRIVATE-VOICE')).json()['id'])
    text=client.get('/api/history/'+job['track_id']+'/metadata').text
    assert 'CONFIDENTIAL' not in text and 'PRIVATE' not in text and 'model_id' not in text
    assert 'sampling' in text


def test_clear_data_preserves_models_and_settings(client):
    wait(client,client.post('/api/jobs',json=payload()).json()['id'])
    ref=client.post('/api/references',content=make_audio()).json()
    assert client.post('/api/privacy/clear').status_code==400
    response=client.post('/api/privacy/clear',headers={'X-Confirm-Clear':'clear-local-history'})
    assert response.status_code==200,response.text
    assert client.get('/api/history').json()['total']==0
    assert client.get('/api/jobs').json()==[]
    assert client.get('/api/presets').json()==[]
    assert client.get('/api/references/'+ref['id']+'/audio').status_code==404
    assert len(client.get('/api/models').json())==3
    assert client.get('/api/preferences').status_code==200


def test_reference_source_name_discarded(client):
    response=client.post('/api/references',content=make_audio(),headers={'X-Filename':'Private-Person-Full-Name.wav'})
    assert response.status_code==201 and 'Private-Person' not in response.text
    ref=response.json()['id']
    assert client.delete('/api/references/'+ref).status_code==200
    assert client.get('/api/references/'+ref+'/audio').status_code==404


def test_log_redaction():
    text=redact('C:\\Users\\ExampleUser\\secret ' + 'hf_' + 'abcdefghijklmnopqrstuvwxyz' + ' contact@example.test')
    assert 'ExampleUser' not in text and 'abcdefghijklmnopqrstuvwxyz' not in text and '@' not in text
    error=public_error(RuntimeError('private prompt and /home/ExampleUser/private.wav'))
    assert 'private prompt' not in error and 'ExampleUser' not in error


def test_config_saved_and_restored(client):
    value=client.get('/api/preferences').json();value.update(discover_hf_cache=False,model_roots=['./models'],remember_drafts=True)
    assert client.put('/api/preferences',json=value).status_code==200
    assert client.get('/api/bootstrap').json()['preferences']['remember_drafts']
