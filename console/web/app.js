let sourceData=null;

async function api(path, options={}){
  const r=await fetch(path,{cache:"no-store",headers:{"Content-Type":"application/json"},...options});
  const d=await r.json();
  if(!r.ok) throw new Error(d.error||d.message||"Request failed");
  return d;
}
function esc(v){return String(v??"").replace(/[&<>"\']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
function msg(v){document.getElementById("message").textContent=v;}
function serviceState(x){return x?.health?.reachable?"RUNNING":(x?.state||"STOPPED");}

function renderReference(d){
  const required=Object.entries(d.required||{});
  const valid=Boolean(d.source_exists&&required.length&&required.every(([,v])=>v));
  const statusClass=d.store_ready?"good":valid?"warn":"bad";
  const checks=required.map(([k,v])=>'<span class="check '+(v?"ok":"")+'">'+esc(k)+': '+(v?"OK":"MISSING")+'</span>').join("");
  const details=d.name==="NSC"
    ? ((d.source_details?.east_files||0)+" EAST · "+(d.source_details?.west_files||0)+" WEST")
    : d.name==="PANS"
      ? ((d.source_details?.xml_files||0)+" XML files")
      : "Datasets + Decode";
  const action=d.store_ready?"UPDATE ROCKSDB":"LOAD ROCKSDB";
  const disabled=valid?"":" disabled";
  const last=d.last_import?(Number.isFinite(Number(d.last_import))?new Date(Number(d.last_import)*1000).toLocaleString():String(d.last_import)):"Not loaded";
  return '<article class="card">'+
    '<div class="card-head"><div><div class="eyebrow">REFERENCE</div><div class="card-title">'+esc(d.name)+'</div></div>'+
    '<span class="badge '+statusClass+'">'+esc(d.status)+'</span></div>'+
    '<div class="field"><label>Source</label><input data-ref="folder" value="'+esc(d.source_folder)+'"><button onclick="browseReference(\''+esc(d.name)+'\')">BROWSE</button></div>'+
    '<div class="checks">'+(checks||'<span class="check">SOURCE NOT MAPPED</span>')+'</div>'+
    '<div class="meta">'+esc(details)+' · '+esc(String(d.files_loaded||0))+' loaded · '+esc(String(d.rows||0))+' rows · '+esc(last)+'</div>'+
    '<div class="card-actions"><button onclick="saveReference(\''+esc(d.name)+'\')">SAVE</button><button onclick="validateReference(\''+esc(d.name)+'\')">VALIDATE</button><button class="primary" onclick="updateReference(\''+esc(d.name)+'\')"' + disabled + '>'+action+'</button></div>'+
    '</article>';
}

async function loadReferenceStatus(){
  const d=await api("/api/reference/status");
  const dbs=d.databases||[];
  document.getElementById("references").innerHTML=dbs.map(renderReference).join("");
}

function referenceCard(name){
  return [...document.querySelectorAll(".card")].find(x=>x.querySelector(".card-title")?.textContent===name);
}
async function saveReference(name){
  const card=referenceCard(name);
  const folder=card.querySelector('[data-ref="folder"]').value.trim();
  try{
    await api("/api/reference/source",{method:"POST",body:JSON.stringify({name,folder})});
    msg(name+" source saved.");
    await loadReferenceStatus();
  }catch(e){msg(e.message);}
}
async function browseReference(name){
  try{
    const r=await api("/api/reference/browse");
    if(r.success){
      referenceCard(name).querySelector('[data-ref="folder"]').value=r.path;
      msg("Folder selected. Click SAVE.");
    }else msg(r.message);
  }catch(e){msg(e.message);}
}
async function validateReference(name){
  try{
    const r=await api("/api/reference/validate",{method:"POST",body:JSON.stringify({name})});
    msg(r.message);
    await loadReferenceStatus();
  }catch(e){msg(e.message);}
}
async function updateReference(name){
  const card=referenceCard(name);
  const button=[...card.querySelectorAll("button")].find(x=>x.textContent.includes("ROCKSDB"));
  if(button){button.disabled=true;button.textContent="UPDATING…";}
  msg(name+" update started: validate → stop Parser → load → restart Parser.");
  try{
    const r=await api("/api/reference/update",{method:"POST",body:JSON.stringify({name})});
    msg(name+" updated: "+((r.manifest?.rows)||0)+" rows. Parser "+(r.parser_restarted?"restarted.":"left stopped.") );
    await refresh();
  }catch(e){
    msg(e.message);
    await refresh();
  }
}

function renderSource(s){
  const c=s.config||{};
  const common=
    '<div class="source-row"><label>Enabled</label><input type="checkbox" data-k="enabled" '+(s.enabled?"checked":"")+'><span></span></div>'+
    '<div class="source-row"><label>Parser</label><select data-k="parser">'+Object.keys(sourceData.parser_destinations||{}).map(x=>'<option value="'+esc(x)+'" '+(x===s.parser?"selected":"")+'>'+esc(x)+'</option>').join("")+'</select><span></span></div>';
  let specific="";
  if(s.type==="file"){
    specific=
      '<div class="source-row"><label>Folder</label><input data-k="folder" value="'+esc(s.folder)+'"><button onclick="browseSource(\''+esc(s.name)+'\')">BROWSE</button></div>'+
      '<div class="source-row"><label>Patterns</label><input data-k="file_patterns" value="'+esc((s.patterns||[]).join(", "))+'"><span></span></div>'+
      '<div class="source-row two"><label>Poll</label><input type="number" step="0.1" data-k="poll_interval_seconds" value="'+esc(s.poll_interval_seconds)+'"><label>Stability</label><input type="number" step="0.1" data-k="stability_window_seconds" value="'+esc(s.stability_window_seconds)+'"></div>';
  }else{
    specific=
      '<div class="source-row"><label>Remote host</label><input data-k="remote_host" value="'+esc(s.host)+'"><span></span></div>'+
      '<div class="source-row two"><label>Port</label><input type="number" data-k="remote_port" value="'+esc(s.port)+'"><label>Framing</label><select data-k="framing"><option value="line" '+(s.framing==="line"?"selected":"")+'>LINE</option><option value="length_prefixed" '+(s.framing==="length_prefixed"?"selected":"")+'>LENGTH</option><option value="raw_block" '+(s.framing==="raw_block"?"selected":"")+'>RAW</option></select></div>';
  }
  return '<article class="source-card '+(s.enabled?"":"disabled")+'">'+
    '<div class="source-top"><span class="source-type">'+esc(s.type.toUpperCase())+'</span><span class="source-name">'+esc(s.name)+'</span><span class="badge '+(s.enabled?"good":"")+'">'+(s.enabled?"ENABLED":"DISABLED")+'</span></div>'+
    '<div class="source-form">'+common+specific+'</div>'+
    '<div class="source-actions"><button onclick="applySource(\''+esc(s.name)+'\')">APPLY</button><span class="path">'+esc(s.type==="file"?(s.exists?"FOLDER OK":"FOLDER MISSING"):(s.host+":"+s.port))+'</span></div>'+
    '</article>';
}
function sourceCard(name){
  return [...document.querySelectorAll(".source-card")].find(x=>x.querySelector(".source-name")?.textContent===name);
}
function sourceVal(card,k){
  const e=card.querySelector('[data-k="'+k+'"]');
  if(!e)return "";
  return e.type==="checkbox"?e.checked:e.value;
}
async function loadSources(){
  sourceData=await api("/api/router/sources");
  const sources=sourceData.sources||[];
  document.getElementById("sources").innerHTML=sources.map(renderSource).join("");
  document.getElementById("router-summary").textContent=sources.length+" sources · "+Object.keys(sourceData.parser_destinations||{}).length+" parser destinations · base "+sourceData.base_dir;
}
async function applySource(name){
  const card=sourceCard(name);
  const s=sourceData.sources.find(x=>x.name===name);
  const body={name,enabled:sourceVal(card,"enabled"),parser:sourceVal(card,"parser")};
  if(s.type==="file"){
    body.folder=sourceVal(card,"folder");
    body.file_patterns=sourceVal(card,"file_patterns").split(",").map(x=>x.trim()).filter(Boolean);
    body.poll_interval_seconds=Number(sourceVal(card,"poll_interval_seconds"));
    body.stability_window_seconds=Number(sourceVal(card,"stability_window_seconds"));
  }else{
    body.remote_host=sourceVal(card,"remote_host");
    body.remote_port=Number(sourceVal(card,"remote_port"));
    body.framing=sourceVal(card,"framing");
  }
  try{
    await api("/api/router/source",{method:"POST",body:JSON.stringify(body)});
    msg(name+" configuration saved. Restart Router to apply.");
    await loadSources();
  }catch(e){msg(e.message);}
}
async function browseSource(name){
  try{
    const r=await api("/api/router/browse");
    if(r.success){
      sourceCard(name).querySelector('[data-k="folder"]').value=r.path;
      msg("Folder selected. Click APPLY.");
    }else msg(r.message);
  }catch(e){msg(e.message);}
}

async function serviceAction(name,action){
  try{
    await api("/api/service/"+name+"/"+action,{method:"POST",body:"{}"});
    msg(name.toUpperCase()+" "+action.toUpperCase()+" requested.");
    setTimeout(refresh,600);
  }catch(e){msg(e.message);}
}

async function refresh(){
  try{
    const d=await api("/api/status");
    for(const n of ["router","parser","forwarder"]){
      const el=document.getElementById(n+"-state");
      const st=serviceState(d.services[n]);
      el.textContent=st;
      el.className=st==="RUNNING"?"good":"";
    }
    document.getElementById("clock").textContent=(d.time||"").split(" ")[1]||"--:--:--";
    document.getElementById("router-status").textContent=JSON.stringify(d.router,null,2);
    await Promise.all([loadSources(),loadReferenceStatus()]);
  }catch(e){msg(e.message);}
}

setInterval(refresh,5000);
refresh();
