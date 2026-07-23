(() => {
  const root = document.querySelector("#portal");
  const form = document.querySelector("#dgt-form");
  const initial = JSON.parse(document.querySelector("#initial-data").textContent);
  const ref = root.dataset.reference;
  const role = root.dataset.role;
  const token = root.dataset.token;
  const api = `/public/tramites/${encodeURIComponent(ref)}/${role}`;
  const steps = [...document.querySelectorAll(".form-step")];
  let step = 1;
  let saveTimer;

  const fields = initial.parte || {};
  const data = fields.datos || {};
  Object.entries({...data, ...fields, ...(initial.vehiculo || {}), ...(initial.operacion || {})}).forEach(([key, value]) => {
    const input = form.elements.namedItem(key);
    if (input && value != null && typeof value !== "object") input.value = value;
  });

  function payload() {
    const raw = Object.fromEntries(new FormData(form).entries());
    const top = {};
    ["tipo_persona", "nombre", "nif", "email", "telefono"].forEach(key => {
      top[key] = raw[key] || "";
      delete raw[key];
    });
    return {...top, datos: raw};
  }

  async function save() {
    const status = document.querySelector("#save-status");
    status.textContent = "Guardando...";
    const response = await fetch(`${api}?token=${encodeURIComponent(token)}`, {
      method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload())
    });
    status.textContent = response.ok ? "Guardado" : "No se pudo guardar";
  }

  function renderStep() {
    steps.forEach(item => item.classList.toggle("hidden", Number(item.dataset.step) !== step));
    document.querySelector("#previous").classList.toggle("hidden", step === 1);
    document.querySelector("#next").classList.toggle("hidden", step === 3);
    document.querySelector("#submit").classList.toggle("hidden", step !== 3);
    document.querySelector("#progress-bar").style.width = `${step * 33.34}%`;
    if (step === 3) {
      const p = payload();
      document.querySelector("#review").innerHTML =
        `<strong>Revisa antes de enviar</strong><span>${p.nombre || "Nombre pendiente"} · ${p.nif || "NIF pendiente"}</span><span>${p.email || "Sin email"} · ${p.telefono || "Sin telefono"}</span>`;
    }
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  form.addEventListener("input", () => {
    document.querySelector("#save-status").textContent = "Cambios pendientes";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => save().catch(() => {}), 800);
  });
  document.querySelector("#next").onclick = async () => { await save(); step++; renderStep(); };
  document.querySelector("#previous").onclick = () => { step--; renderStep(); };

  document.querySelector("#documents").onchange = async event => {
    const list = document.querySelector("#upload-list");
    for (const file of event.target.files) {
      const body = new FormData();
      body.append("tipo", "documentacion");
      body.append("file", file);
      const response = await fetch(`${api}/documentos?token=${encodeURIComponent(token)}`, {method: "POST", body});
      const result = await response.json();
      const line = document.createElement("p");
      line.textContent = response.ok ? `✓ ${result.nombre_archivo}` : `Error: ${result.detail}`;
      list.appendChild(line);
    }
  };

  document.querySelector("#submit").onclick = async () => {
    const message = document.querySelector("#message");
    await save();
    const accepted = document.querySelector("#privacy").checked;
    const response = await fetch(`${api}/submit?token=${encodeURIComponent(token)}&privacy_accepted=${accepted}`, {method: "POST"});
    const result = await response.json();
    if (response.ok) {
      form.innerHTML = `<section class="card"><p class="eyebrow">Enviado correctamente</p><h2>Gracias. Gestinem revisara la informacion.</h2><p>Referencia: <strong>${ref}</strong></p></section>`;
    } else {
      message.textContent = result.detail || "Revisa los datos antes de enviar.";
    }
  };
  renderStep();
})();
