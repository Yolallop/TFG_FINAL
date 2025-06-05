# 🎓 LearningGO – Plataforma Inteligente de Generación de Cursos Educativos

**TFG | Yolanda Llop Pellisa**

🔗 **Visítala en producción:**  
https://learningo-cxa8aac7dmegdhbz.westeurope-01.azurewebsites.net

---

##  Descripción del Proyecto

**LearningGO** es una plataforma web educativa que permite generar **cursos personalizados en vídeo** mediante el uso de Inteligencia Artificial. El sistema analiza las respuestas del usuario a un formulario y crea automáticamente un guion, voz narrada, imágenes y un vídeo tipo YouTube.

Este proyecto está orientado a **facilitar el aprendizaje personalizado** y apoyar la docencia mediante herramientas digitales inteligentes.

---

##  Características Principales

- **Generación de cursos personalizados:**  
  A partir de un formulario con intereses, nivel y objetivos, se genera un vídeo educativo único para el usuario.

- **Narración automatizada:**  
  Usa voz generada automáticamente a partir del guion.

- **Imágenes y vídeo generados por IA:**  
  Cada curso incluye imágenes adaptadas al contenido, todo ensamblado con FFmpeg.

- **Interfaz simple e intuitiva:**  
  Basada en Bootstrap, con panel de usuario, generación de curso, visualización y quizzes automáticos.

---

##  Modelos y Componentes de IA

- **Guion generado con OpenAI (GPT-4 o GPT-3.5)**
- **Imágenes con DALL·E **
- **Voz narrada con gTTS **
- **Vídeo montado con FFmpeg**

---

##  Tecnologías Utilizadas

- **Backend:** Flask, Python 3.10
- **Base de datos:** MongoDB Atlas
- **Frontend:** Bootstrap
- **Servicios IA:** OpenAI, DALL·E, gTTS,FFmpeg
- **Contenedores:** Docker
- **Despliegue:** Azure App Service + Azure Container Registry

##  Requisitos previos

Antes de empezar, asegúrate de tener instalados los siguientes programas en tu máquina:

### Instalacion Python 3.10 o superior

#### ▸ Windows:
- Descarga Python desde [https://www.python.org/downloads/windows](https://www.python.org/downloads/windows)
- Durante la instalación, **marca la casilla "Add Python to PATH"**
- Luego haz clic en “Install Now”

#### ▸ Mac (usando Homebrew):
```bash
brew install python@3.10
```
### ▸ Linux
```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
```
### 1. Clona el repositorio

```bash
git clone https://github.com/tuusuario/learninggo.git
cd TFG_FINAL_CLEAN
```
### 2. Crea y activa el entorno virtual
```bash 
python -m venv .venv
Según tu sistema operativo:
- Windows: .venv\Scripts\activate
- Windows(GitBash): source .venv/Scripts/activate
- Linux/Mac: source .venv/bin/activate
- Windows(GitBash): source .venv/Scripts/activate
```
### 3. Instala las dependencias 
```bash
pip install -r requirements.txt
```
### 4. Ejecución de la aplicación

```bash 
python app.py 

```
### Instrucciones de Despligue con Docker en Azure

La aplicación LearningGO está empaquetada y desplegada en la nube utilizando **Docker**. Todo el código, dependencias y configuración se integran en una imagen Docker personalizada que permite ejecutar la aplicación de forma idéntica tanto en local como en producción.

### ¿Dónde se utiliza Docker?

Docker se usa para:

- Encapsular la aplicación Flask y sus dependencias (Python, FFmpeg, etc.)
- Facilitar la construcción y despliegue automatizado
- Subir la imagen al registro privado de Azure (Azure Container Registry)
- Ejecutar la imagen en Azure App Service como contenedor

### ¿Cómo se usa Docker en este proyecto?

1. Se construye la imagen localmente con:

```bash
docker build -t learningo-app:latest .
```
2. Se etiqueta y sube al Azure Container:
```bash
docker tag learningo-app:latest learningoregistry.azurecr.io/learningo-app:latest
docker push learningoregistry.azurecr.io/learningo-app:latest
```