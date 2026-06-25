#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
from styleframe import StyleFrame
import warnings
import random
import io

warnings.filterwarnings("ignore", category=DeprecationWarning)

def nombre_comision(i, es_espera=False):
    if es_espera:
        return "Espera"
    return str(i)

def procesar_comisiones(materias_info, uploaded_files, df_forzados=None):
    """
    Algoritmo balanceado con soporte para números secuenciales de comisión, 
    límites opcionales por aula y desborde a listas de espera independientes por materia.
    """
    comisiones_forzadas = {}
    if df_forzados is not None:
        for _, r in df_forzados.iterrows():
            leg = str(r["Legajo"])
            coms = [int(x) for x in str(r["Comisiones"]).split(",")]
            comisiones_forzadas[leg] = coms

    # Consolidador y limpiador de archivos de entrada
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

    datos_alumnos = df_all.drop_duplicates(subset="Legajo")[
        ["Legajo", "Alumno", "Estado", "Email", "Teléfono"]
    ]

    # Eliminar duplicados internos por materia
    df_intermedio = df_all.drop_duplicates(subset=["Legajo", "Materia"]).copy()
    df_intermedio["Asiste"] = 1

    pivot = pd.pivot_table(
        df_intermedio, index="Legajo", columns="Materia", values="Asiste", aggfunc="max", fill_value=0
    ).reset_index()

    pivot = pivot.merge(datos_alumnos, on="Legajo", how="left")

    for mat in materias_info:
        if mat not in pivot.columns:
            pivot[mat] = 0

    pivot["N_Materias"] = pivot[list(materias_info.keys())].sum(axis=1)

    alumnos = []
    for _, row in pivot.iterrows():
        materias_cursa = [m for m in materias_info if row[m] > 0]
        alumnos.append({"datos": row, "materias": materias_cursa, "N_Materias": len(materias_cursa)})

    # --- INICIALIZACIÓN DINÁMICA DE ESTRUCTURAS DE COMISIÓN ---
    comisiones = {}
    conteo = {}
    tiene_espera = {}

    for m, info in materias_info.items():
        n = info["n_comisiones"]
        max_alumnos = info["max_alumnos"]
        
        # Evaluar pre-inscripciones totales contra capacidad máxima planificada
        total_inscriptos_materia = sum(1 for a in alumnos if m in a["materias"])
        
        if max_alumnos is not None and total_inscriptos_materia > (n * max_alumnos):
            tiene_espera[m] = True
            total_comisiones_materia = n + 1  # Suma el contenedor de la lista de espera
        else:
            tiene_espera[m] = False
            total_comisiones_materia = n
            
        comisiones[m] = [[] for _ in range(total_comisiones_materia)]
        conteo[m] = [0] * total_comisiones_materia

    # Algoritmo de ruteo balanceado y controlado por cupo
    def asignar_alumnos_balanceado(alumnos_lista):
        random.shuffle(alumnos_lista)
        for alumno in alumnos_lista:
            legajo = str(alumno["datos"]["Legajo"])
            mats = alumno["materias"]
            
            # Caso A: Resolución de Alumnos Forzados
            if legajo in comisiones_forzadas:
                posibles = [c-1 for c in comisiones_forzadas[legajo]]
                idx_com = min(
                    posibles,
                    key=lambda i: sum(conteo[m][i] if i < len(comisiones[m]) else float('inf') for m in mats)
                )
                for m in mats:
                    if idx_com < len(comisiones[m]):
                        comisiones[m][idx_com].append(alumno["datos"])
                        conteo[m][idx_com] += 1
                continue

            # Caso B: Balanceo General óptimo iterando sobre los índices
            max_indice_posible = max(len(comisiones[m]) for m in mats)
            best_idx = None
            min_score = float('inf')
            
            for i in range(max_indice_posible):
                score_actual = 0
                
                for m in mats:
                    if i >= len(comisiones[m]):
                        score_actual += float('inf')
                        continue
                    
                    limite = materias_info[m]["max_alumnos"]
                    es_comision_espera = (tiene_espera[m] and i == len(comisiones[m]) - 1)
                    
                    # Penalización drástica si supera el cupo físico del aula regular
                    if limite is not None and not es_comision_espera and conteo[m][i] >= limite:
                        score_actual += 10000 + conteo[m][i]
                    else:
                        score_actual += conteo[m][i]
                
                if score_actual < min_score:
                    min_score = score_actual
                    best_idx = i
            
            # Asignación efectiva
            for m in mats:
                if best_idx < len(comisiones[m]):
                    comisiones[m][best_idx].append(alumno["datos"])
                    conteo[m][best_idx] += 1

    # Procesar ordenados de mayor a menor según su carga horaria/materia simultánea
    for n_materias in sorted({a["N_Materias"] for a in alumnos}, reverse=True):
        grupo = [a for a in alumnos if a["N_Materias"] == n_materias]
        asignar_alumnos_balanceado(grupo)

    # --- GENERACIÓN DE REPORTES Y EXCEL ---
    output_log = io.StringIO()
    output_log.write("Resumen de inscriptos por comisión:\n")
    for materia, grupos in comisiones.items():
        output_log.write(f"\n{materia}:\n")
        for i, grupo in enumerate(grupos, start=1):
            es_espera_actual = (tiene_espera[materia] and i == len(grupos))
            nom = nombre_comision(i, es_espera=es_espera_actual)
            output_log.write(f"  Comisión {nom}: {len(grupo)} alumnos\n")

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

    # Auditoría de forzados
    errores_forzados = []
    for legajo, coms_permitidas in comisiones_forzadas.items():
        for materia, grupos in comisiones.items():
            for idx, grupo in enumerate(grupos, start=1):
                for alumno in grupo:
                    if str(alumno["Legajo"]) == str(legajo):
                        if idx not in coms_permitidas:
                            es_esp = (tiene_espera[materia] and idx == len(grupos))
                            errores_forzados.append((legajo, materia, nombre_comision(idx, es_esp), coms_permitidas))
    if errores_forzados:
        output_log.write("\n\nERROR en asignación de comisiones forzadas:\n")
        for e in errores_forzados:
            output_log.write(f"  Legajo {e[0]} en {e[1]} quedó en Comisión {e[2]} pero debería estar en {e[3]}\n")
    else:
        output_log.write("\n\nAsignación de comisiones forzadas correcta.\n")

    archivos_salida = {}
    
    # Generar Excels por materia
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
                    es_esp = (tiene_espera[materia] and i == len(grupos))
                    nom_hoja = f"Comision {nombre_comision(i, es_esp)}"
                    sf.to_excel(writer, sheet_name=nom_hoja, best_fit=df.columns.tolist())
        archivos_salida[f"comisiones_{materia.upper().replace(' ', '_')}.xlsx"] = buffer.getvalue()

    # Generar Reporte Matriz de Coherencia Global
    materias_list = list(materias_info.keys())
    registros = []
    for m in materias_list:
        for idx_com, grupo in enumerate(comisiones[m], start=1):
            for alumno in grupo:
                legajo = alumno["Legajo"]
                nombre = alumno["Alumno"]
                es_esp = (tiene_espera[m] and idx_com == len(comisiones[m]))
                nom_com = nombre_comision(idx_com, es_esp)
                
                found = next((r for r in registros if r["Legajo"] == legajo), None)
                if found:
                    found[m] = nom_com
                else:
                    new_r = {"Legajo": legajo, "Alumno": nombre}
                    for mat in materias_list:
                        new_r[mat] = None
                    new_r[m] = nom_com
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

