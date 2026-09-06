const $=id=>document.getElementById(id);
const rupiah=n=>new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(Number(n)||0);
const rawMoney=value=>{const digits=String(value??"").replace(/\D/g,"");return digits?Number(digits):0};
const formatMoneyInput=value=>{const n=rawMoney(value);return n?new Intl.NumberFormat("id-ID",{maximumFractionDigits:0}).format(n):""};
const month=()=>$("monthPicker").value;
let chart=null;

function toast(msg){$("toast").textContent=msg;$("toast").classList.remove("hidden");clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>$("toast").classList.add("hidden"),2400)}
async function api(url,opts={}){const r=await fetch(url,{headers:{"Content-Type":"application/json",...(opts.headers||{})},...opts});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||"Terjadi kesalahan.");return d}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
function formatDateID(value){if(!value)return "-";const d=new Date(value+"T00:00:00");return Number.isNaN(d.getTime())?value:d.toLocaleDateString("id-ID",{day:"numeric",month:"long",year:"numeric"})}
function todayISO(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`}
function openModal(id){$(id).classList.remove("hidden")}
function closeModal(id){$(id).classList.add("hidden")}

function setupMoneyInputs(){
  document.querySelectorAll(".money-field").forEach(input=>{
    input.addEventListener("input",()=>{const pos=input.selectionStart;input.value=formatMoneyInput(input.value);try{input.setSelectionRange(input.value.length,input.value.length)}catch{}});
    input.addEventListener("blur",()=>input.value=formatMoneyInput(input.value));
  });
}
function setMoney(id,value){$(id).value=value?formatMoneyInput(value):""}
function openTxModal(tx=null){
  $("txModalTitle").textContent=tx?"Edit transaksi":"Tambah transaksi";
  $("txId").value=tx?.id||"";
  $("txKind").value=tx?.kind||"expense";$("txName").value=tx?.name||"";setMoney("txAmount",tx?.amount||"");
  $("txCategory").value=tx?.category||"Lainnya";$("txDate").value=tx?.transaction_date||todayISO();$("txNote").value=tx?.note||"";
  openModal("txModal");
}
function openGoalModal(){$("goalForm").reset();setMoney("goalSaved",0);openModal("goalModal")}
function openRecurringModal(){$("recurringForm").reset();$("recDay").value=10;openModal("recurringModal")}

async function load(){
  try{
    const s=await api(`/api/summary?month=${encodeURIComponent(month())}`);
    $("balance").textContent=rupiah(s.balance);$("income").textContent=rupiah(s.income);$("expense").textContent=rupiah(s.expense);
    $("budgetValue").textContent=rupiah(s.budget);setMoney("budgetInput",s.budget||"");
    if(s.budget){
      const pct=Math.min(100,Math.max(0,s.expense/s.budget*100));$("budgetProgress").style.width=pct+"%";
      $("budgetProgress").parentElement.classList.toggle("warn",pct>=75&&pct<90);$("budgetProgress").parentElement.classList.toggle("danger",pct>=90);
      $("budgetText").textContent=pct>=100?`Budget terlampaui ${rupiah(s.expense-s.budget)}.`:`Terpakai ${pct.toFixed(0)}% · Sisa ${rupiah(Math.max(0,s.budget-s.expense))}.`;
      $("budgetLeft").textContent=rupiah(s.budget_left);
    }else{$("budgetProgress").style.width="0";$("budgetText").textContent="Belum ada budget.";$("budgetLeft").textContent="Belum diatur"}
    renderChart(s.categories);renderCategoryStats(s.categories);
    renderTx(await api(`/api/transactions?month=${encodeURIComponent(month())}`));
    await loadCategoryBudgets();await loadGoals();await loadRecurring();
    $("exportBtn").href=`/export.csv?month=${encodeURIComponent(month())}`;
  }catch(e){toast(e.message)}
}
function renderTx(rows){
  const body=$("txBody");body.innerHTML="";$("emptyTx").classList.toggle("hidden",rows.length>0);
  rows.forEach(t=>{
    const tr=document.createElement("tr");const sign=t.kind==="income"?"+":"-";const cls=t.kind==="income"?"positive":"negative";
    tr.innerHTML=`<td>${formatDateID(t.transaction_date)}</td><td><span class="tx-name">${esc(t.name)}</span>${t.note?`<span class="tx-note">${esc(t.note)}</span>`:""}</td><td>${esc(t.category)}</td><td class="${cls}">${sign} ${rupiah(t.amount)}</td><td><div class="mini-actions"><button onclick='openTxModal(${JSON.stringify(t)})'>Edit</button><button onclick="removeTx(${t.id})">Hapus</button></div></td>`;
    body.appendChild(tr);
  });
}
async function removeTx(id){if(!confirm("Hapus transaksi ini?"))return;try{await api(`/api/transactions/${id}`,{method:"DELETE"});toast("Transaksi dihapus.");load()}catch(e){toast(e.message)}}
function renderChart(categories){
  const ctx=$("expenseChart");if(chart)chart.destroy();
  if(!categories.length){ctx.getContext("2d").clearRect(0,0,ctx.width,ctx.height);return}
  chart=new Chart(ctx,{type:"doughnut",data:{labels:categories.map(x=>x.category),datasets:[{data:categories.map(x=>x.total),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:"70%",plugins:{legend:{position:"bottom",labels:{boxWidth:9,padding:13,font:{size:10}}}}}});
}
function renderCategoryStats(cats){$("categoryStats").innerHTML=cats.slice(0,5).map(x=>`<div class="category-line"><span>${esc(x.category)}</span><span>${rupiah(x.total)}</span></div>`).join("")||'<div class="empty">Belum ada pengeluaran.</div>'}
async function loadCategoryBudgets(){
  const rows=await api(`/api/category-budgets?month=${encodeURIComponent(month())}`);const el=$("catBudgetList");
  el.innerHTML=rows.map(r=>`<div class="list-row"><div class="row-top"><strong>${esc(r.category)}</strong><span>${rupiah(r.amount)}</span></div></div>`).join("")||'<div class="empty">Belum ada budget kategori.</div>';
}
async function loadGoals(){
  const rows=await api("/api/goals");const el=$("goalsList");$("emptyGoals").classList.toggle("hidden",rows.length>0);el.innerHTML="";
  rows.forEach(g=>{const pct=Math.min(100,(g.saved/g.target)*100);const div=document.createElement("div");div.className="goal";
    div.innerHTML=`<div class="goal-top"><span>${esc(g.name)}</span><span>${pct.toFixed(0)}%</span></div><div class="progress"><span style="width:${pct}%"></span></div><small>${rupiah(g.saved)} dari ${rupiah(g.target)}${g.deadline?" · "+formatDateID(g.deadline):""}</small><div class="goal-actions"><button class="remove-btn" onclick="updateGoalPrompt(${g.id},${JSON.stringify(g)})">Update</button><button class="remove-btn" onclick="removeGoal(${g.id})">Hapus</button></div>`;
    el.appendChild(div);
  });
}
async function updateGoalPrompt(id,g){
  const saved=prompt(`Tabungan saat ini untuk ${g.name}:`,formatMoneyInput(g.saved));if(saved===null)return;
  try{await api(`/api/goals/${id}`,{method:"PUT",body:JSON.stringify({...g,saved:rawMoney(saved),target:g.target})});toast("Target diperbarui.");loadGoals()}catch(e){toast(e.message)}
}
async function removeGoal(id){if(!confirm("Hapus target ini?"))return;try{await api(`/api/goals/${id}`,{method:"DELETE"});toast("Target dihapus.");loadGoals()}catch(e){toast(e.message)}}
async function loadRecurring(){
  const rows=await api("/api/recurring");const el=$("recurringList");
  el.innerHTML=rows.map(r=>`<div class="recurring-item"><div class="row-top"><strong>${esc(r.name)}</strong><span class="${r.kind==="income"?"positive":"negative"}">${r.kind==="income"?"+":"-"} ${rupiah(r.amount)}</span></div><small>${esc(r.category)} · setiap tanggal ${r.day_of_month}</small><button class="remove-btn" onclick="removeRecurring(${r.id})">Hapus</button></div>`).join("")||'<div class="empty">Belum ada transaksi berulang.</div>';
}
async function removeRecurring(id){if(!confirm("Hapus transaksi berulang?"))return;try{await api(`/api/recurring/${id}`,{method:"DELETE"});toast("Transaksi berulang dihapus.");loadRecurring()}catch(e){toast(e.message)}}

$("monthPicker").addEventListener("change",load);
$("txForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const id=$("txId").value;
  const amount=rawMoney($("txAmount").value);
  if(!amount){toast("Masukkan nominal yang valid.");return}
  const data={kind:$("txKind").value,name:$("txName").value,amount,category:$("txCategory").value,note:$("txNote").value,transaction_date:$("txDate").value};
  try{await api(id?`/api/transactions/${id}`:"/api/transactions",{method:id?"PUT":"POST",body:JSON.stringify(data)});closeModal("txModal");toast(id?"Transaksi diperbarui.":"Transaksi ditambahkan.");load()}catch(e){toast(e.message)}
});
$("budgetForm").addEventListener("submit",async e=>{
  e.preventDefault();const amount=rawMoney($("budgetInput").value);if(!amount){toast("Masukkan budget yang valid.");return}
  try{await api("/api/budget",{method:"POST",body:JSON.stringify({month:month(),amount})});toast("Budget disimpan.");load()}catch(e){toast(e.message)}
});
$("catBudgetForm").addEventListener("submit",async e=>{
  e.preventDefault();const amount=rawMoney($("catBudgetAmount").value);if(!amount){toast("Masukkan nominal budget kategori.");return}
  try{await api("/api/category-budget",{method:"POST",body:JSON.stringify({month:month(),category:$("catBudgetCategory").value,amount})});$("catBudgetAmount").value="";toast("Budget kategori disimpan.");loadCategoryBudgets()}catch(e){toast(e.message)}
});
$("goalForm").addEventListener("submit",async e=>{
  e.preventDefault();const target=rawMoney($("goalTarget").value);if(!target){toast("Masukkan target yang valid.");return}
  try{await api("/api/goals",{method:"POST",body:JSON.stringify({name:$("goalName").value,target,saved:rawMoney($("goalSaved").value),deadline:$("goalDeadline").value})});closeModal("goalModal");toast("Target dibuat.");loadGoals()}catch(e){toast(e.message)}
});
$("recurringForm").addEventListener("submit",async e=>{
  e.preventDefault();const amount=rawMoney($("recAmount").value);if(!amount){toast("Masukkan nominal yang valid.");return}
  try{await api("/api/recurring",{method:"POST",body:JSON.stringify({kind:$("recKind").value,name:$("recName").value,amount,category:$("recCategory").value,day_of_month:Number($("recDay").value)})});closeModal("recurringModal");toast("Transaksi berulang disimpan.");loadRecurring()}catch(e){toast(e.message)}
});
document.querySelectorAll(".modal").forEach(m=>m.addEventListener("click",e=>{if(e.target===m)m.classList.add("hidden")}));
setupMoneyInputs();load();
