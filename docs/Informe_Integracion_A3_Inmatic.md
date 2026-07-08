# Informe técnico: cómo Inmatic se integra con A3 (a3ASESOR / A3ECO–A3CON de Wolters Kluwer)

**Objetivo:** documentar en detalle el mecanismo de enlace de Inmatic con A3 para que puedas replicarlo en tu propia aplicación de escritorio en Python: (1) leer y escribir el plan contable en ambas direcciones, (2) capturar el número de asiento tras contabilizar facturas, y (3) entender el mecanismo de conexión.

**Fuente analizada:** `C:\Users\GestinemFiscal\Desktop\inmatic_extracted`, principalmente el paquete `python_worker/plugins/a3/` (código real de producción en Python).

---

## 1. Conclusión clave sobre el mecanismo de conexión

**A3 NO se conecta por SQL Server, ni por ODBC/DSN, ni por Pervasive SQL vía cliente.** No hay cadena de conexión, ni usuario/contraseña, ni driver de base de datos. El connector "de base de datos" está literalmente vacío:

```python
# python_worker/plugins/a3/connector.py
class A3DataLoopConnector(InmaticConnector):
    def get_db(self):
        pass
        # self.con = mysql.connector.connect(...)   <-- comentado, no se usa
```

La integración con A3 se hace **a nivel de sistema de ficheros**, en dos direcciones distintas y con dos técnicas distintas:

| Dirección | Técnica | Qué se toca |
|-----------|---------|-------------|
| **Leer de A3** (plan contable, terceros, empresas, asientos) | Se **leen y decodifican directamente los ficheros binarios `.DAT`** de A3 (formato tipo Btrieve/Pervasive de registro fijo). Se parsean byte a byte según offsets conocidos. | `*CU.DAT`, `TCLIPRO.DAT`, `TECODIR.DAT`, `*A.DAT` |
| **Escribir a A3** (altas de cuentas/terceros, facturas con IVA, vencimientos, pagos) | Se **generan ficheros de "enlace" en texto plano de ancho fijo** (formato de importación estándar de a3ASESOR|eco|con) y se depositan en la carpeta de enlace. A3 los importa desde su propia utilidad de enlace/importación. | fichero `{EMPRESA}.DAT` en `files_directory` |

Es decir: **la lectura es intrusiva (parseo binario directo de los ficheros de A3), y la escritura es no intrusiva (se usa el formato oficial de importación de A3).**

### 1.1. Parámetros de "conexión" (rutas, no credenciales)

Definidos en `python_worker/plugins/a3/config.py`:

```python
class A3Config:
    directory = 'C:\\A3\\A3ECO'      # carpeta raíz de la instalación A3ECO
    split_invoices_a3 = True          # partir facturas con muchas líneas
    files_directory = None            # carpeta donde se dejan los ficheros de ENLACE (importación)
```

- `directory` (`con_directory_a3` en la configuración de usuario) es la raíz de A3ECO. Ejemplos reales vistos en los tests: `C:\A3\A3ECO`, `E:\a3\a3eco`, `E:\prg\a3\a3eco`, `\\DESKTOP-XXXX\A3software\A3\A3ECO\`, `C:\Datos Tous\ApliA3\A3\A3ECO\`. Puede ser una unidad local o un **recurso de red UNC**.
- `files_directory` es la carpeta de enlace (donde A3 lee los ficheros de importación). Si no se especifica, se usa `os.path.join(self.directory, '..')` (el padre de A3ECO).
- No hay ningún otro secreto: **el "acceso" es simplemente tener permiso de lectura/escritura sobre esas carpetas de Windows.** (De hecho, `python_worker/config_contanet.md` muestra que la integración se apoya en crear un usuario Windows local con permisos sobre las carpetas: `net user inmatic ... /ADD`, `icacls ... /grant inmatic:(OI)(CI)F /T`.)

### 1.2. Tecnología de la app

- **Worker de integración: Python** (todo el paquete `python_worker/`, empaquetado con PyInstaller — ver `inmatic.spec`, `build.py`). Usa `pandas` para tratar los registros como DataFrames.
- **Carcasa de escritorio: Electron / Node.js** (`main.js`, `preload.js`, `package.json`, `node_modules/`). El proceso Node lanza el worker Python (`contanet_connector.exe` / `inmatic_service.exe`).
- **No se usa ninguna DLL de terceros para hablar con A3.** No hay dependencia de Btrieve/Pervasive SDK. El formato binario se decodifica "a mano" en Python puro (`a3_read.py`). Las DLLs que ves en la carpeta `contasol/` (C1FlexGrid, FormsDELSOL, etc.) son de **otro** conector (ContaSOL/Sage DELSOL), no de A3.

---

## 2. Estructura de ficheros de A3 relevante

A3ECO organiza los datos por **empresa** y **ejercicio**. El código del ejercicio es el **último dígito del año** (`id_ejercicio = ejercicio % 10`; p. ej. 2024 → `4`, 2025 → `5`).

```
{directory}\                         (p.ej. C:\A3\A3ECO)
├── TECODIR.DAT                       Directorio de EMPRESAS (código, nombre, carpeta, CIF, nº dígitos)
├── TCLIPRO.DAT                       Maestro de TERCEROS (clientes/proveedores): cod_tercero, CIF, nombre
└── E00666\  (carpeta de la empresa)  <- la ruta real se obtiene de TECODIR.DAT
    ├── 006661CU.DAT                  PLAN CONTABLE (Cuentas) de la empresa 00666, ejercicio 1
    ├── 006661OA.DAT                  ASIENTOS del ejercicio 1, mes "O" (octubre)
    ├── 0066615A.DAT                  ASIENTOS del ejercicio 1, mes 5 (mayo)
    └── FACTURAS\{año}\               PDFs de las facturas que Inmatic deposita
```

### Convención de nombres de fichero

- **Plan contable (cuentas):** `{empresa5}{id_ejercicio}CU.DAT`
  Código real: `f'{codigo_emp[1:]}{id_ejercicio}CU.DAT'` → para `E00666` y ejercicio `1` → `006661CU.DAT`. (`CU` = Cuentas.)
- **Asientos (apuntes) por mes:** `{empresa5}{id_ejercicio}{cod_mes}A.DAT`
  Código real: `f'{company_code}{ejercicio_code}{month_code}A.DAT'` → `006661OA.DAT`. (`A` = Asientos.)
- **Código de mes** (`get_month_code`): meses 1–9 = `'1'..'9'`; **octubre = `'O'`, noviembre = `'N'`, diciembre = `'I'`**. Ese detalle es fácil de pasar por alto y es imprescindible para localizar el fichero de asientos correcto.

### Resolución de la carpeta de la empresa

La carpeta física de cada empresa **no** se asume; se lee de `TECODIR.DAT` (campo `carpeta`) y luego se normaliza con la unidad/recurso de `directory`:

```python
# a3_read.py
def get_carpeta_empresa(num_empresa):
    empresas = A3File(f'{config.directory}\\TECODIR.DAT', EmpresaRecord, fixed_record_length=1032)
    df = empresas.to_dataframe()
    df = df[df['codigo'] == num_empresa]
    df = df[df['status'] == 4]           # status==4 = registro activo/válido
    return df.iloc[0].carpeta

def get_carpeta_a3(num_empresa, ...):    # combina la unidad de config.directory con la carpeta de la empresa
    ...
```

`get_base_dir`/`get_carpeta_a3` existen para reconciliar rutas cuando A3 guarda la carpeta como `\A3\A3ECO\E06813` pero la instalación real está en `E:\prg\a3\a3eco` o en un UNC. Si replicas esto, replica esa lógica o simplifícala si tus rutas son estables.

---

## 3. Formato binario de los `.DAT` (para LEER de A3)

Cada `.DAT` es un fichero tipo **Btrieve/Pervasive de longitud de registro fija**, con una **cabecera de 128 bytes** seguida de registros. La clase base `A3File` (`a3_read.py`) lo lee entero, lo pasa a hexadecimal y trocea por longitud de registro:

```python
class A3File:
    def __init__(self, filename, record_class, is_index=False, fixed_record_length=None, record_kwargs={}):
        self.content = binascii.hexlify(open(filename,'rb').read()).decode('ascii')
        self.header  = self.content[:128*2]     # 128 bytes de cabecera
        self.content = self.content[128*2:]
        self.parse_header()

    def parse_header(self):
        self.maximum_length = int_from_hexa(self.header, 54*2, 58*2)   # longitud de registro
        self.minimum_length = int_from_hexa(self.header, 58*2, 62*2)
        if not self.record_length:
            self.record_length = self.maximum_length*2 + 8*(not self.is_index)
        assert self.maximum_length == self.minimum_length              # registro fijo
```

Detalles importantes de decodificación:
- Los enteros se leen big-endian por defecto; algunos campos son **little-endian** (sufijo `_le` en la definición) y se invierten con `transform_le`.
- Las cadenas se decodifican en **`latin-1`** (¡no UTF-8!).
- El campo `status` (byte 0 de cada registro) filtra registros vivos: **`status == 4`** = registro activo/válido. En terceros además se descarta `cod_tercero == 0`.
- Las longitudes de registro que el código fija a mano cuando no se autodetectan: `TECODIR.DAT` = **1032**, `TCLIPRO.DAT` = **536** (terceros).

### 3.1. Registro de CUENTA — plan contable (`AccountRecord`, fichero `*CU.DAT`)

Definición real (offset en **bytes** dentro del registro, longitud en bytes, tipo):

| Campo | Tipo | Offset | Long | Significado |
|-------|------|--------|------|-------------|
| `status` | int | 0 | 1 | 4 = activo |
| `size` | int | 1 | 3 | tamaño |
| `cuenta_mayor` | int | 4 | 4 | parte "mayor" de la cuenta |
| `subcuenta` | int | 8 | 8 | parte "subcuenta" |
| `cuenta` | calc | — | — | cuenta final compuesta (ver abajo) |
| `name` | str | 16 | 60 | descripción de la cuenta |
| `cod_tercero` | int **_le** | 424 | 8 | enlace al tercero (TCLIPRO) |
| `contrapartida` | int **_le** | 432 | 10 | cuenta de contrapartida |
| `tipo_op1/2/3` | int | 457/459/461 | 1 | tipo de operación (ámbito IVA) |
| `por_iva1/2/3` | int | 463/465/467 | 1 | código % IVA |
| `por_ret/2/3` | int | 469/471/473 | 1 | código de retención |

Composición de la cuenta (`calc_fields`), que resuelve el nº de dígitos del plan:

```python
if cuenta_mayor == 0:
    cuenta = str(subcuenta).ljust(4,'0'); num_zeros = 8
else:
    cuenta = str(cuenta_mayor).ljust(4,'0') + str(subcuenta).rjust(8,'0')
    cuenta = cuenta[:num_digits]        # recorta al nº de dígitos del plan (normalmente 8..12)
```

El **número de dígitos del plan contable** de la empresa se deduce de las cuentas existentes:
```python
num_digits = 12 - int(cuentas.to_dataframe()['num_zeros'].min())   # get_num_digits()
```

### 3.2. Registro de TERCERO (`TercerosRecord`, fichero `TCLIPRO.DAT`, long. fija 536)

| Campo | Tipo | Offset | Long |
|-------|------|--------|------|
| `status` | int | 0 | 1 |
| `cod_tercero` | int | 4 | 8 |
| `cif` | str | 12 | 28 |
| `name` | str | 40 | 60 |

`TCLIPRO.DAT` usa una lectura especial (`TercerosFile.__iter__`) que avanza en bloques de 520 y tiene lógica de "descorrupción" si detecta desalineamiento.

### 3.3. Registro de EMPRESA (`EmpresaRecord`, fichero `TECODIR.DAT`, long. fija 1032)

| Campo | Tipo | Offset | Long | Significado |
|-------|------|--------|------|-------------|
| `codigo` | int | 4 | 6 | código de empresa (p.ej. 666) |
| `empresa` | str | 10 | 60 | nombre |
| `cif` | str | 98 | 28 | CIF |
| `carpeta` | str | 206 | 60 | ruta física de la carpeta de la empresa |
| `digitos` | int | 991 | 2 | nº de dígitos del plan |

### 3.4. Registro de ASIENTO/APUNTE (`AsientoRecord`, fichero `*A.DAT`) — clave para el nº de asiento

| Campo | Tipo | Offset | Long | Significado |
|-------|------|--------|------|-------------|
| `status` | int | 0 | 1 | |
| `date` | int | 5 | 7 | fecha `AAAAMMDD` |
| `concepto` | str | 30 | 60 | concepto del apunte (Inmatic mete aquí `{id}.{descr}`) |
| **`apunte`** | int | **222** | **6** | **número de asiento** |
| `account` | int | 110 | 10 | cuenta |
| `num_fra` | str | 90 | 20 | número de factura |
| `deber_haber` | str | 120 | 2 | `D`/`H` |
| `importe` | hex | 126 | 24 | importe codificado (signo en penúltimo nibble: `7`=negativo, `3`=positivo) |

Decodificación del importe (útil si necesitas cuadrar apuntes):
```python
signo = -1 if importe[-2:-1] == '7' else 1
value = int(str_from_hexa(importe, 0, -4))
decimals = float(importe[-3::2]) / 100
calculated_import = signo * (value + decimals)
```

---

## 4. Escribir a A3: ficheros de "enlace" de ancho fijo (para ALTAS/ESCRITURA)

Toda escritura hacia A3 (altas de cuentas/terceros, facturas con IVA, vencimientos, pagos, descripciones SII) se hace generando registros de **texto de 512 caracteres** (posiciones 1–510 de datos + `\r\n` final), codificados en `latin-1`, y **acumulándolos en un fichero `.DAT` de enlace** que A3 importa después con su utilidad de enlace.

Motor genérico (`utils.py`):

```python
class Registro:
    def __init__(self):
        self.text_list = [" "] * 510 + ["\r", "\n"]     # registro de 512 chars
    def set_data(self, **kwargs):
        kwargs['se-ci-tipform'] = '5'                    # tipo de formato = constante 5
        # coloca cada campo en su (posición, longitud) con su formato
    def get_bytes(self):
        return self.get_text().encode('latin-1')

class A3Link:
    def dump_data(self, file_name):
        with open(file_name, 'ab') as f:                 # se AÑADE (append) al fichero de enlace
            f.write(self.get_bytes())
```

Nombre del fichero de enlace (`get_enlace_file`): `os.path.join(config.files_directory, f'{codigo_emp}.DAT')` (o `{empresa}{actividad}.DAT` si hay actividad). Ej.: `...\E00666.DAT`.

Cada tipo de registro tiene su tabla de posiciones (todas en `utils.py`). Todas empiezan por:
- pos 1, `se-ci-tipform` = `'5'` (constante).
- pos 2 (long 5), `se-ci-codemp` = código de empresa con ceros (`00666`).
- pos 7 (long 8), fecha `AAAAMMDD`.
- pos 15, `se-ci-tipreg` = tipo de registro (distinto por cada tabla, ver abajo).
- pos 16 (long 12), `se-ci-cuenta` = cuenta **nivel 6 a 12, rellena a 12 con ceros a la derecha** (`.ljust(12,'0')`).
- pos 510, `se-ci-generado` = `'N'`.

### 4.1. Alta/modificación de CUENTA o TERCERO en el plan contable (escritura del plan contable → A3)

Tabla `CODES_CU_THIRD` → clase `RegistroCUThird`. **`se-ci-tipreg` (pos 15) = `'C'`.** Campos relevantes:

| Posición | Long | Campo | Descripción |
|----------|------|-------|-------------|
| 16 | 12 | `se-ci-cuenta` | **cuenta a dar de alta o modificar. Si no existe, A3 la crea automáticamente en el plan contable.** |
| 28 | 30 | `se-ci-descuenta` | descripción de la cuenta |
| 58 | 1 | `se-ci-act-saldo-inicial` | S/N actualizar saldo inicial |
| 59 | 14 | `se-ci-saldo-inicial` | saldo inicial (float con signo) |
| 78 | 14 | `se-ci-nif` | NIF del tercero |
| 94 | 30 | `se-ci-via` | dirección |
| 135 | 20 | `se-ci-municipio` | municipio |
| 155 | 5 | `se-ci-cp` | código postal |
| 160 | 15 | `se-ci-provincia` | provincia |
| 241 | 12 | `se-ci-cuenta-contra` | cuenta de contrapartida (nivel 6–12) |
| 255 | 2 | `se-ci-tipo-doc` | tipo de documento (02 = NIF-IVA…) |
| 509 | 1 | `se-ci-moneda` | `E` euros / `P` pesetas |

Uso real (`repositories/thirdyparty.py`, `process_thirdy_party`): se construye un `RegistroCUThird` con estos campos y se vuelca al fichero de enlace. **Este es exactamente el mecanismo para "escribir el plan contable a A3": generar registros tipo `C` y dejarlos en la carpeta de enlace para que A3 los importe.** Si la cuenta no existe, A3 la crea; si existe, la modifica.

### 4.2. Otros registros que Inmatic escribe (contexto de facturación)

- **Cabecera de factura con IVA** — `CODES_CABECERA_IVA` / `RegistroCabeceraIVA`, `se-ci-tipreg`: `'1'` factura, `'2'` rectificativa; `se-ci-tipfac`: `1` ventas, `2` compras, `3` bienes de inversión. Incluye `se-ci-numfac`, importe total, CIF/nombre tercero, fechas de operación y factura, y **`se-ci-numsii`** (nº de factura ampliado para el SII).
- **Línea de IVA** — `CODES_LINEA_IVA` / `RegistroLineaIVA`, `se-ci-tipreg` = `'9'`; base, % IVA, cuota, recargo, retención, subtipo de factura, cuenta de IVA soportado/repercutido, etc. La última línea del asiento se marca `se-ci-linea = 'U'` (las intermedias `'M'`).
- **Línea de asiento manual** (para pagos automáticos) — `CODES_LINEA_ASIENTO` / `RegistroLineaAsiento`, `se-ci-tipreg` = `'0'`, con `se-ci-tipimporte` `D`/`H`.
- **Vencimiento** (cartera de cobros/pagos) — `CODES_VENCIMIENTO` / `RegistroVencimiento`, `se-ci-tipreg` = `'V'`.
- **Descripción de factura / SII** — `CODES_DESCRIPTION_INVOICE` / `RegistroDescriptionInvoice`, `se-ci-tipreg` = `'5'`.

El flujo completo de una factura está en `repositories/invoice.py::load_invoice_aux`: crea la cabecera, N líneas de IVA, opcionalmente descripción SII, vencimiento y apuntes de pago, y hace `link.dump_data(get_enlace_file(...))`. Devuelve `{'invoice_id':…, 'state':'pending_sync'}` — es decir, **al escribir el fichero de enlace la factura queda "pendiente de sincronizar"; el número de asiento todavía no existe** (se obtiene después, ver sección 5).

Nota sobre formato numérico (`float_with_zeros_sign` en `utils.py`): los importes van como `+` o `-` seguido del número con 2 decimales, rellenado con ceros a la izquierda hasta 13 (14 si negativo). Los porcentajes de IVA (`float_two_decimals`) van con 2 decimales rellenos a 5. **Respeta estos formatos exactamente** o A3 rechazará el registro.

---

## 5. Capturar el número de asiento tras contabilizar una factura

Este es el punto 2 de tu objetivo. El mecanismo (`repositories/invoice.py`):

1. Inmatic escribe el enlace de la factura (sección 4) → factura en estado `pending_sync`. **No hay retorno directo del número de asiento**: A3 no devuelve nada al importar.
2. Más tarde (proceso de sincronización), Inmatic **lee el fichero binario de asientos del mes** y busca la factura por su concepto para leer el campo `apunte` (= número de asiento).

```python
def find_entry_number(self, invoice):
    found = False
    for month in '123456789ONDI':                      # prueba todos los meses (incluye O,N,I)
        found, asiento = self.find_entry_number_by_date(invoice, month)
        if found:
            break
    return found, asiento

def find_entry_number_by_date(self, invoice, month_code):
    company_code  = str(int(invoice['company_contanet'][1:])).zfill(5)   # 'E00666' -> '00666'
    _, _, year    = invoice['accounting_date'].split('/')
    ejercicio_code = int(year) % 10
    file_name = f'{company_code}{ejercicio_code}{month_code}A.DAT'        # p.ej. 006661OA.DAT
    carpeta   = get_carpeta_a3(int(invoice['company_contanet'].replace('E','')))
    asiento_file = os.path.join(carpeta, file_name)

    asientos = A3File(asiento_file, AsientoRecord)
    df = asientos.to_dataframe()
    # El 'concepto' del apunte contiene "{invoice_id}.{descripcion}"; se casa por invoice_id:
    asiento = df[df['concepto'].apply(lambda x: x.split('.')[0]) == str(invoice['id'])].iloc[0]['apunte']
    return True, str(asiento)
```

Puntos críticos para replicarlo:
- **La correlación factura ↔ asiento se hace por el campo `concepto` del apunte.** Inmatic, al escribir la factura, pone en la descripción (`se-ci-desfac`) el valor `descr = str(invoice['id']) + '.' + descripción`. Ese mismo `id` aparece luego en el `concepto` del asiento generado por A3, y es la clave para recuperarlo. **Si en tu app quieres poder recuperar el asiento, incrusta un identificador único tuyo en la descripción del apunte.**
- El `apunte` (offset 222, 6 bytes, entero) es el **número de asiento** que buscas.
- Hay que **barrer los 12 meses** (`'123456789ONDI'`) porque no se sabe de antemano en qué fichero mensual acabó el asiento.
- Este proceso es **asíncrono respecto a la escritura**: primero A3 tiene que haber importado el enlace (el usuario o un job ejecuta el enlace en A3), y sólo entonces el asiento existe en el `*A.DAT`.

---

## 6. Flujo completo (resumen operativo)

**Leer plan contable de A3 (A3 → tu app):**
1. Abrir `TECODIR.DAT` → localizar empresa por `codigo`, obtener `carpeta` y `cif`.
2. Abrir `{empresa}{ejercicio}CU.DAT` con el layout `AccountRecord` → cuentas + descripción + enlaces a tercero/contrapartida.
3. Abrir `TCLIPRO.DAT` con `TercerosRecord` → CIF/nombre de cada tercero.
4. Cruzar cuentas con terceros por `cod_tercero` (ver `get_merged_accounts`) para las cuentas de grupos 40/41/43/44/523/173.
5. Filtrar siempre por `status == 4`.

**Escribir plan contable / altas a A3 (tu app → A3):**
1. Construir registros tipo `C` (`RegistroCUThird`/`CODES_CU_THIRD`) con cuenta, descripción, NIF, dirección, contrapartida, etc.
2. Volcar (append) al fichero de enlace `{files_directory}\{EMPRESA}.DAT` en `latin-1`.
3. Ejecutar el enlace/importación en A3 (paso propio de A3). Cuentas nuevas se crean, existentes se modifican.

**Contabilizar factura y recuperar asiento:**
1. Escribir cabecera IVA (`1`/`2`) + líneas IVA (`9`) + opcional vencimiento (`V`)/pago (`0`)/descripción (`5`) al fichero de enlace, con el `invoice_id` incrustado en `se-ci-desfac`.
2. A3 importa el enlace → genera el asiento.
3. Leer `{empresa}{ejercicio}{mes}A.DAT` con `AsientoRecord`, casar por `concepto`→`invoice_id`, leer `apunte` = número de asiento.

---

## 7. Cómo implementarlo en Python (recomendaciones concretas)

Buena noticia: **el código de Inmatic ya es Python puro y no depende de ningún driver.** Puedes reutilizar el enfoque casi tal cual.

- **No necesitas `pyodbc`, `pypyodbc`, `sqlalchemy` ni un motor Pervasive/Btrieve** para el enfoque que usa Inmatic, porque no hay servidor SQL: se leen/escriben ficheros. Bastan `struct`/`binascii` y `pandas` (opcional).
  - `pyodbc`/`sqlalchemy` sólo te harían falta si decides atacar A3 vía un **motor Pervasive/Btrieve real por ODBC** (existe el driver "Pervasive PSQL / Actian Zen ODBC"). Es una alternativa más "limpia" para leer, pero: (a) requiere que el motor Pervasive esté instalado y con DSN configurado, (b) para **escribir** el plan contable e insertar facturas de forma soportada por Wolters Kluwer **igualmente deberías usar el fichero de enlace** (escribir directamente en los `.DAT` de A3 con SQL no está soportado y es arriesgado). Por eso Inmatic optó por parseo binario para leer y enlace de texto para escribir.
- **Lectura binaria:** replica `A3File`/`A3Record`. Puntos a respetar: cabecera de 128 bytes, `record_length = maximum_length*2 + 8` (cuando no es índice), campos `_le` en little-endian, cadenas en `latin-1`, filtro `status==4`, longitudes fijas conocidas (`TECODIR`=1032, `TCLIPRO`=536). Puedes hacerlo con `struct.unpack` en lugar de hex si prefieres.
- **Escritura de enlace:** replica `Registro`/`A3Link`. Registro de 512 bytes (`510 + \r\n`), relleno de espacios, `latin-1`, campos por posición/longitud, formatos numéricos `float_with_zeros_sign`/`float_two_decimals` exactos, `append` al fichero `{EMPRESA}.DAT`.
- **Recuperación de asiento:** replica `find_entry_number` barriendo `'123456789ONDI'` y casando por el identificador que tú incrustes en la descripción.
- **Librerías Python sugeridas:** `pandas` (cómodo para cruces cuentas↔terceros; opcional), nada más para el core. Si vas por ODBC/Pervasive: `pyodbc` + DSN "Actian Zen/Pervasive PSQL".
- **Codificación:** SIEMPRE `latin-1` (ISO-8859-1), tanto al leer como al escribir. Nunca UTF-8.
- **Permisos:** tu proceso necesita permiso de lectura sobre la carpeta A3ECO y de escritura sobre la carpeta de enlace (`files_directory`). En red, montar el UNC con credenciales adecuadas (patrón `net user` + `icacls` visto en `config_contanet.md`).

### Esqueleto mínimo en Python (lectura de cuentas)

```python
import binascii, pandas as pd

def leer_dat(path, definition, record_length=None, header=128):
    raw = binascii.hexlify(open(path, 'rb').read()).decode('ascii')
    content = raw[header*2:]
    if record_length is None:
        max_len = int(raw[54*2:58*2], 16)     # de la cabecera
        record_length = max_len*2 + 8
    n = len(content) // record_length
    filas = []
    for i in range(n):
        reg = content[i*record_length:(i+1)*record_length]
        fila = {}
        for nombre, tipo, off, ln in definition:      # offsets/long en BYTES
            h = reg[off*2:(off+ln)*2]
            if tipo == 'int':
                fila[nombre] = int(h, 16) if h else 0
            elif tipo == 'str':
                fila[nombre] = bytes.fromhex(h).decode('latin-1').strip()
        filas.append(fila)
    return pd.DataFrame(filas)

CUENTA_DEF = [('status','int',0,1), ('cuenta_mayor','int',4,4),
              ('subcuenta','int',8,8), ('name','str',16,60)]
df = leer_dat(r'C:\A3\A3ECO\E00666\006661CU.DAT', CUENTA_DEF)
df = df[df['status'] == 4]
```

(Para `cod_tercero`/`contrapartida` recuerda invertir los bytes: son little-endian.)

---

## 8. Advertencias y riesgos

- **Escribir directamente en los `.DAT` de A3 no está soportado y puede corromper la base de datos.** El diseño de Inmatic evita esto: sólo escribe mediante ficheros de enlace en el formato oficial de A3. Haz lo mismo.
- El parseo binario de lectura depende de la **versión de A3**; los offsets están calibrados para A3ECO/a3ASESOR|eco|con. Si tu instalación difiere, valida los offsets contra ficheros reales (compara con lo que muestra A3).
- La recuperación del asiento **sólo funciona después** de que A3 haya ejecutado el enlace; el número no es inmediato.
- Verifica el nº de dígitos del plan (8–12) por empresa: condiciona el `ljust(12,'0')` de las cuentas y el recorte en lectura.
- Los ficheros del proyecto `contanet.exe`, `contanet_connector.exe`, `inmatic*.exe` son binarios PyInstaller; **el código fuente Python de la sección `python_worker/plugins/a3/` es la fuente de verdad** y es lo que se ha analizado aquí (no hizo falta desensamblar los .exe).

---

## Apéndice — Archivos fuente relevantes

| Archivo | Contenido |
|---------|-----------|
| `python_worker/plugins/a3/config.py` | Rutas de A3 (`directory`, `files_directory`), sin credenciales |
| `python_worker/plugins/a3/a3_read.py` | Lectura binaria: `A3File`, `AccountRecord`, `TercerosRecord`, `EmpresaRecord`, `AsientoRecord`, resolución de carpetas |
| `python_worker/plugins/a3/utils.py` | Tablas de posiciones de enlace (`CODES_*`), motor `Registro`/`A3Link`, lógica IVA/ámbito/retención, `get_num_digits`, nombres de fichero |
| `python_worker/plugins/a3/repositories/account.py` | Lectura del plan contable + carga de maestro de cuentas/terceros hacia Inmatic |
| `python_worker/plugins/a3/repositories/thirdyparty.py` | Escritura de altas de cuenta/tercero (registro tipo `C`) al enlace |
| `python_worker/plugins/a3/repositories/invoice.py` | Escritura de factura al enlace + `find_entry_number` (captura del nº de asiento) |
| `python_worker/plugins/a3/repositories/connector.py` | Datos de empresa (NIF, nombre, nº dígitos) desde `TECODIR.DAT` + `*CU.DAT` |
| `python_worker/plugins/a3/test_a3.py` | Tests con datos y rutas reales de ejemplo (empresa `E00666`, meses, carpetas) |
| `fixtures/a3/A3ECO/TECODIR.DAT`, `.../E00666/006661OA.DAT` | Ficheros `.DAT` de ejemplo para pruebas |
