/** @typedef {{enroll(course:string):Promise<object>, modules():Promise<string[]>,
 *  advance(m:string):Promise<object>, locateAssessment():Promise<object>,
 *  captureCompletion():Promise<{certId:string,payload:string}>}} Adapter */

const _registry = new Map();
export function registerAdapter(name, adapter) { _registry.set(name, adapter); }
export function getAdapter(name) {
  const a = _registry.get(name);
  if (!a) throw new Error(`no adapter registered: ${name}`);
  return a;
}
