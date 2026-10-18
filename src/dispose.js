// Frees GPU memory held by a loaded model, including textures attached to its materials.
export function disposeObject(object) {
  const textures = new Set();
  const materials = new Set();
  const geometries = new Set();
  object.traverse(node => {
    if (node.geometry) geometries.add(node.geometry);
    for (const material of node.material ? [node.material].flat() : []) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  textures.forEach(texture => texture.dispose());
  materials.forEach(material => material.dispose());
  geometries.forEach(geometry => geometry.dispose());
}
