#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
from styleframe import StyleFrame
import warnings
import random
import io

warnings.filterwarnings("ignore", category=DeprecationWarning)

def nombre_comision(i):
    n = (i + 1) // 2
    letra = "A" if i % 2 == 1 else "B"
    return f"{n}{letra}"

def procesar_comisiones(materias_info, uploaded_files, df_forzados=None):
    """
    Lógica principal adaptada para Streamlit.
    - Corrige el problema de alumnos duplicados en la misma materia (cuenta como 1).
    """
    comisiones_forzadas = {}
    if df_forzados is not None:
        for _, r in df_forzados.iterrows():
            leg = str(r["Legajo"])
            coms = [int(x) for x in str(r["Comisiones"]).split(",")]
            comisiones_forzadas[leg] = coms

    # Lectura y unificación
    dfs = []
    for materia, archivos in uploaded_files.items():
        for archivo in archivos:
            df = pd.read_excel(archivo)
            df["Materia"] = materia
            dfs.append(df)

    if not dfs:
        return None, "No se subieron archivos válidos.", None

    df_all = pd.concat(dfs, ignore_index=True)
    df_all["Alumno"] = df_all["Alumno"].str.strip()

    cols = ["Estado", "Email", "Teléfono"]
    for c in cols:
        if c in df_all.columns:
            df_all[c] = df_all[c].fillna("-").replace("", "-")
        else:
            df_all[c] = "-"

    # Guardar los datos únicos generales de los alumnos
    datos_alumnos = df_all.drop_duplicates(subset="Legajo")[
        ["Legajo", "Alumno", "Estado", "Email", "Teléfono"]
    ]

    # --- CAMBIO CLAVE AQUÍ ---
    # Eliminamos duplicados de Legajo + Materia. Si un alumno está en 2 archivos de la misma materia, queda 1 sola vez.
    df_intermedio = df_all.drop_duplicates(subset=["Legajo", "Materia"]).copy()
    df_intermedio["Asiste"] = 1  # Marcador de presencia fija

    # Pivotamos usando 'max' sobre la columna 'Asiste' para asegurar que sea 1 o 0
    pivot = pd.pivot_table(
        df_intermedio, index="Legajo", columns="Materia", values="Asiste", aggfunc="max", fill_value=0
    ).reset_index()
    # --------------------------

    pivot = pivot.merge(datos_alumnos, on="Legajo", how="left")

    for mat in materias_info:
        if mat not in pivot.columns:
            pivot[mat] = 0

    pivot["N_Materias"] = pivot[list(materias_info.keys())].sum(axis=1)

    alumnos = []
    for _, row in pivot.iterrows():
        materias_cursa = [m for m in materias_info if row[m] > 0]
        alumnos.append({"datos": row, "materias": materias_cursa, "N_Materias": len(materias_cursa)})

    comisiones = {m: [[] for _ in range(n)] for m, n in materias_info.items()}
    conteo = {m: [0]*n for m, n in materias_info.items()}

    # Algoritmo de asignación
    def asignar_alumnos_balanceado(alumnos_lista):
        random.shuffle(alumnos_lista)
        for alumno in alumnos_lista:
            legajo = str(alumno["datos"]["Legajo"])
            mats = alumno["materias"]
            
            if legajo in comisiones_forzadas:
                posibles = [c-1 for c in comisiones_forzadas[legajo]]
                idx_com = min(
                    posibles,
                    key=lambda i: sum(conteo[m][i] if i < materias_info[m] else float('inf') for m in mats)
                )
                for m in mats:
                    if idx_com < materias_info[m]:
                        comisiones[m][idx_com].append(alumno["datos"])
                        conteo[m][idx_com] += 1
                continue

            idx_com = min(
                range(max(materias_info[m] for m in mats)),
                key=lambda i: sum(conteo[m][i] if i < materias_info[m] else float('inf') for m in mats)
            )
            for m in mats:
                if idx_com < materias_info[m]:
                    comisiones[m][idx_com].append(alumno["datos"])
                    conteo[m][idx_com] += 1

    for n_materias in sorted({a["N_Materias"] for a in alumnos}, reverse=True):
        grupo = [a for a in alumnos if a["N_Materias"] == n_materias]
        asignar_alumnos_balanceado(grupo)

    # Captura de consola/reporte de texto
    output_log = io.StringIO()
    output_log.write("Resumen de inscriptos por comisión:\n")
    for materia, grupos in comisiones.items():
        output_log.write(f"\n{materia}:\n")
        for i, grupo in enumerate(grupos, start=1):
            output_log.write(f"  Comisión {nombre_comision(i)}: {len(grupo)} alumnos\n")

    todos_legajos = set()
    for grupos in comisiones.values():
        for grupo in grupos:
            for alumno in grupo:
                todos_legajos.add(alumno["Legajo"])
                
    output_log.write("\nEstadísticas generales:\n")
    output_log.write(f"  Total de alumnos únicos: {len(todos_legajos)}")

    for materia, grupos in comisiones.items():
        total_materia = sum(len(grupo) for grupo in grupos)
        output_log.write(f"\n  Total de inscriptos en {materia}: {total_materia}")

    # Verificación de forzados en el log
    errores_forzados = []
    for legajo, coms_permitidas in comisiones_forzadas.items():
        for materia, grupos in comisiones.items():
            for idx, grupo in enumerate(grupos, start=1):
                for alumno in grupo:
                    if str(alumno["Legajo"]) == str(legajo):
                        if idx not in coms_permitidas:
                            errores_forzados.append((legajo, materia, idx, coms_permitidas))
    if errores_forzados:
        output_log.write("\n\nERROR en asignación de comisiones forzadas:\n")
        for e in errores_forzados:
            output_log.write(f"  Legajo {e[0]} en {e[1]} quedó en {nombre_comision(e[2])} pero debería estar en {e[3]}\n")
    else:
        output_log.write("\n\nAsignación de comisiones forzadas correcta.\n")

    # Generación de Excels en memoria (Bytes)
    archivos_salida = {}
    
    # Excels por materia
    for materia, grupos in comisiones.items():
        buffer = io.BytesIO()
        with StyleFrame.ExcelWriter(buffer) as writer:
            for i, grupo in enumerate(grupos, start=1):
                if grupo:
                    df = pd.DataFrame(grupo)
                    df = df.sort_values(by="N_Materias", ascending=False)
                    for mat in materias_info:
                        if mat in df.columns:
                            df[mat] = df[mat].replace({1: "SI", 0: "NO"})
                    sf = StyleFrame(df)
                    sf.to_excel(writer, sheet_name=f"Comision {nombre_comision(i)}", best_fit=df.columns.tolist())
        archivos_salida[f"comisiones_{materia.upper().replace(' ', '_')}.xlsx"] = buffer.getvalue()

    # Reporte de Coherencia
    materias_list = list(materias_info.keys())
    registros = []
    for m in materias_list:
        for idx_com, grupo in enumerate(comisiones[m], start=1):
            for alumno in grupo:
                legajo = alumno["Legajo"]
                nombre = alumno["Alumno"]
                found = next((r for r in registros if r["Legajo"] == legajo), None)
                if found:
                    found[m] = nombre_comision(idx_com)
                else:
                    new_r = {"Legajo": legajo, "Alumno": nombre}
                    for mat in materias_list:
                        new_r[mat] = None
                    new_r[m] = nombre_comision(idx_com)
                    registros.append(new_r)

    df_coh = pd.DataFrame(registros)
    df_coh["Comision_Coincide"] = df_coh.apply(
        lambda row: len(set([row[m] for m in materias_list if row[m] is not None])) == 1, axis=1
    )
    
    buffer_coh = io.BytesIO()
    sf_coh = StyleFrame(df_coh)
    with StyleFrame.ExcelWriter(buffer_coh) as writer:
        sf_coh.to_excel(writer, best_fit=df_coh.columns.tolist())
    
    archivos_salida["reporte_coherencia_comisiones.xlsx"] = buffer_coh.getvalue()

    return archivos_salida, output_log.getvalue(), df_coh
