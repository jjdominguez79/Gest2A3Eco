# Catalogo territorial

`municipios_ine_2026.csv` contiene la relacion oficial de municipios del INE a
1 de enero de 2026. Se genera desde
`https://www.ine.es/daco/daco42/codmun/26codmun.xlsx` mediante:

```powershell
python tool/generar_catalogo_municipios.py `
  tmp/26codmun.xlsx backend/api/data/municipios_ine_2026.csv
```

El fichero se incluye en el backend para que la busqueda de territorios no
dependa de que el INE este disponible en el momento de uso.
