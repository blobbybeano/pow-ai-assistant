const CACHE = 'powwash-v2';
const SHELL = ['/', '/login'];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL).catch(() => {}))
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname === '/login' || url.pathname === '/logout') {
    e.respondWith(fetch(e.request));
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => {
      const network = fetch(e.request).then(res => {
        if (res.ok && e.request.method === 'GET') {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
      return cached || network;
    })
  );
});

const NOTIF_ICONS = {
  customer_message: '/static/icons/icon-192.png',
  human_input:      '/static/icons/icon-192.png',
  booking_complete: '/static/icons/icon-192.png',
};

const NOTIF_BADGES = '/static/icons/icon-192.png';

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) {}

  const type  = data.type  || 'customer_message';
  const title = data.title || 'PowWash';
  const body  = data.body  || 'You have a new notification.';
  const tone  = data.tone  || type;
  const url   = data.url   || '/';

  e.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon:  NOTIF_ICONS[type] || NOTIF_ICONS.customer_message,
      badge: NOTIF_BADGES,
      tag:   type,
      data:  { url, tone },
      requireInteraction: type === 'human_input',
      vibrate: type === 'human_input' ? [200, 100, 200, 100, 200] : [150],
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if ('focus' in client) { client.focus(); return; }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
