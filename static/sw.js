/**
 * Audio Bible Service Worker
 * Caches the app shell for faster loading and basic offline support.
 */
const CACHE_NAME = 'audio-bible-v1';
const PRECACHE_URLS = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/manifest.json',
];

// Install: cache app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// Fetch: network-first for API, cache-first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // API calls: always go to network
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() =>
                new Response(JSON.stringify({ 
                    error: 'You are offline. Please check your internet connection.',
                    text: 'No internet connection. Please try again.',
                    has_audio: false 
                }), {
                    headers: { 'Content-Type': 'application/json' }
                })
            )
        );
        return;
    }
    
    // Static assets: cache-first
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) {
                // Return cached, but also update cache in background
                fetch(event.request).then(response => {
                    if (response.ok) {
                        caches.open(CACHE_NAME).then(cache => {
                            cache.put(event.request, response);
                        });
                    }
                }).catch(() => {});
                return cached;
            }
            return fetch(event.request).then(response => {
                // Cache new static assets
                if (response.ok && (url.pathname.startsWith('/static/') || url.pathname === '/')) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            });
        })
    );
});
