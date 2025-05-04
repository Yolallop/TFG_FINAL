# backfill_provenance.py
from pymongo import MongoClient
from config import GOOGLE_API_KEY
import googleapiclient.discovery
import hashlib
from datetime import datetime

client = MongoClient("mongodb://localhost:27017")
db = client.tfg_db
vids = db.videos

def fact_check_claim(claim: str):
    svc = googleapiclient.discovery.build(
      'factchecktools','v1alpha1', developerKey=GOOGLE_API_KEY)
    resp = svc.claims().search(query=claim, languageCode='es').execute()
    return resp.get('claims', [])

for v in vids.find({'show_provenance': False}):
    texto = v['script']
    ruta_video = f"static/videos/{v['video_path']}"
    vid_id = v['_id']

    # 1) Fact-check
    raw = fact_check_claim(texto)
    verified = []
    for c in raw:
        reviews = c.get('claimReview',[])
        if reviews:
            verified.append({
                'text':   c.get('text','')[:200],
                'url':    reviews[0].get('url'),
                'rating': reviews[0]['reviewRating'].get('text')
            })

    # 2) Blockchain hash
    with open(ruta_video,'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()

    # 3) Fecha de firma
    fecha = datetime.utcnow().isoformat()

    # 4) Update en Mongo
    vids.update_one(
      {'_id': vid_id},
      {'$set': {
         'fact_checks':      verified,
         'blockchain_hash':  h,
         'firma_fecha':      fecha,
         'show_provenance':  True
      }}
    )
    print(f"Procesado vídeo {vid_id}")
