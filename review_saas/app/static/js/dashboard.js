
async function loadKpis(companyId){
  const token = localStorage.getItem('token')||'';
  const params = new URLSearchParams(companyId?{company_id:companyId}:{})
  const r = await fetch('/dashboard/kpis?'+params.toString(),{headers:{'Authorization':'Bearer '+token}});
  const j = await r.json();
  document.getElementById('k1')?.innerText = j.total_reviews||0;
  document.getElementById('k2')?.innerText = j.avg_rating||0;
  document.getElementById('k3')?.innerText = `${j.mix?.positive||0}/${j.mix?.neutral||0}/${j.mix?.negative||0}`;
  // trend
  if(companyId){
    const t = await fetch('/dashboard/trend?company_id='+companyId,{headers:{'Authorization':'Bearer '+token}})
    const tj = await t.json();
    const ctx = document.getElementById('trend'); if(!ctx) return;
    new Chart(ctx,{type:'line',data:{labels:tj.labels||[],datasets:[{label:'Avg Rating',data:tj.data||[]}]}});
  }
}
