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
  let invoiceUploaded = Boolean(initial.factura_aportada);

  const fields = initial.parte || {};
  const data = fields.datos || {};
  Object.entries({...data, ...fields, ...(initial.vehiculo || {}), ...(initial.operacion || {})}).forEach(([key, value]) => {
    const input = form.elements.namedItem(key);
    if (input && value != null && typeof value !== "object") {
      if (input.type === "checkbox") input.checked = ["on", "true", "1"].includes(String(value).toLowerCase());
      else input.value = value;
    }
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

  function juridical() {
    return form.elements.namedItem("tipo_persona").value === "juridica";
  }

  function toggleConditionalFields() {
    const representative = document.querySelector("#representative-fields");
    representative.classList.toggle("hidden", !juridical());
    representative.querySelectorAll("input").forEach(input => input.required = juridical());
    const upload = document.querySelector("#invoice-upload");
    if (upload) {
      const visible = role === "vendedor" && juridical();
      upload.classList.toggle("hidden", !visible);
      document.querySelector("#invoice").required = visible && !invoiceUploaded;
    }
    const loads = form.elements.namedItem("cargas_estado");
    const loadsDetail = document.querySelector("#loads-detail");
    if (loads && loadsDetail) {
      const visible = loads.value === "con_cargas";
      loadsDetail.classList.toggle("hidden", !visible);
      loadsDetail.querySelector("textarea").required = visible;
    }
  }

  function copyShippingAddress() {
    const same = document.querySelector("#same-address");
    if (!same) return;
    const mapping = {
      direccion_envio: "direccion",
      cp_envio: "cp",
      poblacion_envio: "poblacion",
      provincia_envio: "provincia",
    };
    Object.entries(mapping).forEach(([targetName, sourceName]) => {
      const target = form.elements.namedItem(targetName);
      if (same.checked) target.value = form.elements.namedItem(sourceName).value;
      target.readOnly = same.checked;
    });
  }

  async function save() {
    const status = document.querySelector("#save-status");
    status.textContent = "Guardando...";
    const response = await fetch(`${api}?token=${encodeURIComponent(token)}`, {
      method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload())
    });
    status.textContent = response.ok ? "Guardado" : "No se pudo guardar";
    return response.ok;
  }

  function validateCurrentStep() {
    toggleConditionalFields();
    const current = steps[step - 1];
    const invalid = [...current.querySelectorAll("input, select, textarea")].find(input => !input.checkValidity());
    if (invalid) {
      invalid.reportValidity();
      invalid.focus();
      return false;
    }
    return true;
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
    toggleConditionalFields();
    copyShippingAddress();
    document.querySelector("#save-status").textContent = "Cambios pendientes";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => save().catch(() => {}), 800);
  });
  document.querySelector("#next").onclick = async () => {
    if (!validateCurrentStep()) return;
    await save();
    step++;
    renderStep();
  };
  document.querySelector("#previous").onclick = () => { step--; renderStep(); };

  const invoiceInput = document.querySelector("#invoice");
  invoiceInput.onchange = async event => {
    const list = document.querySelector("#upload-list");
    for (const file of event.target.files) {
      const body = new FormData();
      body.append("tipo", "factura");
      body.append("file", file);
      const response = await fetch(`${api}/documentos?token=${encodeURIComponent(token)}`, {method: "POST", body});
      const result = await response.json();
      const line = document.createElement("p");
      line.textContent = response.ok ? `✓ ${result.nombre_archivo}` : `Error: ${result.detail}`;
      list.appendChild(line);
      invoiceUploaded = response.ok;
      toggleConditionalFields();
    }
  };

  document.querySelector("#submit").onclick = async () => {
    const message = document.querySelector("#message");
    if (!validateCurrentStep()) return;
    await save();
    const accepted = document.querySelector("#privacy").checked;
    const response = await fetch(`${api}/submit?token=${encodeURIComponent(token)}&privacy_accepted=${accepted}`, {method: "POST"});
    const result = await response.json();
    if (response.ok) {
      form.innerHTML = `<section class="card"><p class="eyebrow">Enviado correctamente</p><h2>Gracias. Gestinem revisara la informacion.</h2><p>Referencia: <strong>${ref}</strong></p></section>`;
    } else {
      const detail = Array.isArray(result.detail) ? result.detail.join(" ") : result.detail;
      message.textContent = detail || "Revisa los datos antes de enviar.";
    }
  };
  form.elements.namedItem("tipo_persona").addEventListener("change", toggleConditionalFields);
  const sameAddress = document.querySelector("#same-address");
  if (sameAddress) sameAddress.addEventListener("change", copyShippingAddress);
  const loads = form.elements.namedItem("cargas_estado");
  if (loads) loads.addEventListener("change", toggleConditionalFields);
  toggleConditionalFields();
  copyShippingAddress();
  renderStep();
})();
