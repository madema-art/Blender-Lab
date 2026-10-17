import { resolve, relative, sep } from 'node:path';

export default {
  plugins: [{
    name: 'reload-repository-models',
    configureServer(server) {
      const modelsDir = resolve(process.cwd(), 'public/models');
      server.watcher.add(modelsDir);
      server.watcher.on('all', (event, file) => {
        const normalized = file.split(sep).join('/');
        const modelsPrefix = modelsDir.split(sep).join('/') + '/';
        if (!normalized.startsWith(modelsPrefix)) return;
        const relativePath = relative(modelsDir, file).split(sep).join('/');
        if (relativePath === 'manifest.json' || /\.(?:glb|gltf|bin|png|jpe?g|webp|ktx2)$/i.test(relativePath)) {
          server.ws.send({ type: 'full-reload', path: '*' });
        }
      });
    }
  }]
};
