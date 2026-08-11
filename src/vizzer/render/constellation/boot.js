// codex-sequence-2026-08-08: a boot failure must be visible, including parse
// errors in the generated application script below.
(function(){
  const boot=document.getElementById('boot');
  function fail(detail){
    boot.hidden=false; boot.className='error';
    boot.textContent='Vizzer could not start.\n'+(detail||'Unknown browser error');
  }
  addEventListener('error',function(event){
    fail(event&&(event.message||(event.error&&event.error.message)));
  },true);
  addEventListener('unhandledrejection',function(event){
    const reason=event&&event.reason;
    fail(reason&&(reason.message||String(reason)));
  });
  window.__vizzerBoot={ready:function(){boot.hidden=true;},fail:fail};
})();
