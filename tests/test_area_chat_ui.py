import pytest

@pytest.mark.parametrize("saved_before_failure", [True, False])
def test_lost_post_response_reconciles_after_reopening(saved_before_failure):
    from pathlib import Path
    import subprocess
    source=Path('src/vizzer/render/constellation/dossier.js').read_text()
    source=source[source.index('async function openPlanningArea'):source.index('if(SERVED)setTimeout(loadPlanningAreas')]
    setup='const savedBeforeFailure='+str(saved_before_failure).lower()+';'+r'''
    let activePlanningArea=null,areaRequest=0,sel=-1;
    const areaDrafts=new Map(),areaPending=new Map(),esc=x=>x,renderStoryMarkdown=x=>x;
    const document={documentElement:{classList:{add(){}}}};
    const dossier={classList:{add(){},contains(){return true}},setAttribute(){}};
    const dossierIdentity={},dossierFooter={};let form,input,status,messages,send;
    const dbody={set innerHTML(value){
     input={value:''};status={};messages={};send={};
     form={isConnected:true,querySelector:s=>s==='textarea'?input:send};
    },querySelector:s=>s==='.areamessages'?messages:s==='.areastatus'?status:form,querySelectorAll:()=>[]};
    let stored=[],counter=0,fail=true;const crypto={randomUUID:()=>`id-${++counter}`};
    function setTimeout(){}
    async function fetch(url,options){
     if(options){if(fail&&!savedBeforeFailure){fail=false;throw Error('request did not reach server');}const body=JSON.parse(options.body);stored.push({...body,author:'Owner',createdAt:new Date().toISOString()});if(fail){fail=false;throw Error('response lost after save');}}
     return {ok:true,json:async()=>({title:'Test',project:'Test',messages:stored.slice(),pending:stored.length,csrfToken:'x'})};
    }
    '''
    run=r'''
    (async()=>{
     await openPlanningArea('test');input.value='Plan v0';input.oninput();
     await form.onsubmit({preventDefault(){}});
     const first=status.textContent;
     await openPlanningArea('test');
     await form.onsubmit({preventDefault(){}});
     if(stored.length!==1)throw Error('duplicate question after reopen');
     if(counter!==1)throw Error('retry used a new request identity');
     if(input.value!=='')throw Error('saved question left in composer');
    })();
    '''
    subprocess.run(['node','-e',setup+source+run],text=True,capture_output=True,check=True,timeout=5)
