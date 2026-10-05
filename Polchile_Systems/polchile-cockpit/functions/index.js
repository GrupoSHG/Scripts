const functions = require('firebase-functions');
const admin     = require('firebase-admin');
const fetch     = require('node-fetch');

admin.initializeApp();

exports.getDashboardData = functions
  .region('us-central1')
  .https.onRequest(async (req, res) => {

    // 1. CORS
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');
    if (req.method === 'OPTIONS') { res.status(204).send(''); return; }

    // 2. Verificar token Firebase Auth
    const idToken = (req.headers.authorization || '').replace('Bearer ', '');
    if (!idToken) return res.status(401).json({ error: 'Token requerido' });
    try {
      await admin.auth().verifyIdToken(idToken);
    } catch (err) {
      return res.status(403).json({ error: 'Token inválido' });
    }

    // 3. Llamar al Apps Script
    const appsScriptUrl = functions.config().polchile.apps_script_url;
    try {
      const response = await fetch(`${appsScriptUrl}?action=data`);
      const data     = await response.json();
      return res.json(data);
    } catch (err) {
      return res.status(500).json({ error: 'Error al obtener datos' });
    }
  });