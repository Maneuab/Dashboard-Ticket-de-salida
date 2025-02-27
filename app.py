import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import base64
from io import BytesIO
import matplotlib.pyplot as plt
import os
import io
import re
import jupyter_dash
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from dash import Output, Input

# Define el alcance de la API
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Cargar credenciales desde la variable de entorno
creds_json = os.getenv('GOOGLE_CREDENTIALS')

if creds_json:
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
else:
    raise ValueError("Las credenciales de Google no están definidas en la variable de entorno.")

# Construir el servicio de Google Drive
service = build('drive', 'v3', credentials=credentials)

# ID de la carpeta compartida
folder_id = '1O1LrNyYThQKXQ0aWzx3TGdK1pmwdb-5C'

# Inicializa una lista para guardar los dataframes
all_dfs = []

# Obtén la lista de archivos en la carpeta, including mimeType
results = service.files().list(q=f"'{folder_id}' in parents",
                                fields="nextPageToken, files(id, name, mimeType)").execute() # Include mimeType in fields
items = results.get('files', [])


# Procesa cada archivo
for item in items:
    # Check for Google Sheets files (ending with .gsheet)
    if item['name'].endswith(".gsheet") or item['mimeType'] == 'application/vnd.google-apps.spreadsheet':
        # Get the file ID
        file_id = item['id']

        # Download the file content as CSV
        request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            _, done = downloader.next_chunk()
        fh.seek(0)

        # Read the CSV content into a pandas DataFrame
        df_temp = pd.read_csv(fh)

        # Extraer solo el nombre de la materia eliminando el prefijo y sufijo
        materia_name = re.sub(r'^Ticket de Salida - | \(respuestas\)$', '', item['name'])
        df_temp["Materia"] = materia_name  # Agregar columna con el nombre limpio de la materia
        all_dfs.append(df_temp)

# Check if all_dfs is empty before concatenation
if all_dfs:
    df = pd.concat(all_dfs, ignore_index=True)
else:
    print("No se encontraron archivos .gsheet en la carpeta de Google Drive. La lista all_dfs está vacía.")
    df = pd.DataFrame() # For example, create an empty DataFrame


# Ordenar los datos de mayor a menor aceptación
df_grouped = df.groupby("Materia")["Mi satisfacción con la clase fue..."].agg(["mean", "count"])
df_grouped = df_grouped.rename(columns={"mean": "Puntaje Promedio", "count": "Número de Respuestas"}).reset_index()
df_grouped = df_grouped.sort_values(by="Puntaje Promedio", ascending=False)
#print(df_grouped)


# Procesar datos de satisfacción agrupando por materia
df_grouped = df.groupby("Materia")["Mi satisfacción con la clase fue..."].agg(["mean", "count"])
df_grouped = df_grouped.rename(columns={"mean": "Puntaje Promedio", "count": "Número de Respuestas"}).reset_index()
df_grouped = df_grouped.sort_values(by=['Puntaje Promedio'], ascending=True)


# Obtener los estudiantes con menor puntuación promedio
df_students = df.groupby("Dirección de correo electrónico")["Mi satisfacción con la clase fue..."].mean().reset_index()
df_students = df_students.rename(columns={"Mi satisfacción con la clase fue...": "Puntaje Promedio"})
df_students = df_students.sort_values(by="Puntaje Promedio", ascending=True)

# Inicializar la aplicación Dash
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Dashboard de Ticket de Salida"),

    html.H3("Ranking de Materias por Aceptación"),

    dcc.Graph(
        id='ranking-materias',
        figure=px.bar(df_grouped, x='Puntaje Promedio', y='Materia',
                      orientation='h', title='Ranking de Todas las Materias',
                      text_auto=True).update_layout(
    height=800,  # Adjust the height as needed
    margin=dict(l=200, r=50, t=50, b=50)
    )),

    dcc.Graph(
        id='histograma-satisfaccion',
        figure=px.histogram(df, x='Mi satisfacción con la clase fue...', nbins=10,
                            title='Distribución de Puntuaciones de Satisfacción')
    ),
    html.H3("Calificación Promedio por Estudiante"),
    dcc.Graph(
        id='ranking-estudiantes',
        figure=px.bar(df_students, x='Puntaje Promedio', y='Dirección de correo electrónico',
                      orientation='h', title='Estudiantes que calificaron menos en promedio',
                      text_auto=True).update_layout(
    height=1200,  # Adjust the height as needed
    margin=dict(l=200, r=50, t=50, b=50), yaxis={'categoryorder':'total descending'}
    )),

    html.H3("Preguntas y Comentarios Frecuentes"),
    dcc.Dropdown(
        id='materia-dropdown',
        options=[{'label': materia, 'value': materia} for materia in df['Materia'].unique()],
        value=df['Materia'].unique()[0]  # Set initial value
    ),
     html.Div(id='lista-preguntas-container'),


])

from dash import Output, Input
@app.callback(
    Output('lista-preguntas-container', 'children'),
    Input('materia-dropdown', 'value')
)
def update_preguntas(selected_materia):
    preguntas = df[df['Materia'] == selected_materia]["¿Tienes alguna pregunta que te gustaría que sea respondida la siguiente clase?"].dropna().unique()
    return html.Ul([html.Li(pregunta) for pregunta in preguntas])

if __name__ == '__main__':
    app.run_server(debug=True)

server = app.server  # Necesario para Gunicorn en Render

