/** @typedef {{navigate(u:string):Promise<{payload:string}>, click(s:string):Promise<{payload:string}>,
 *  fill(s:string,v:string):Promise<{payload:string}>, waitFor(s:string):Promise<{payload:string}>,
 *  capture(k:string):Promise<{kind:string,payload:string}>, snapshot():Promise<{url:string,fields:object}>}} Driver */

// Deterministic offline driver for tests + dry runs. Records every call in `actions`.
export class FakeDriver {
  constructor() { this.actions = []; this._url = "about:blank"; this._fields = {}; }
  async navigate(u) { this.actions.push("navigate:" + u); this._url = u; return { payload: "navigated:" + u }; }
  async click(s) { this.actions.push("click:" + s); return { payload: "clicked:" + s }; }
  async fill(s, v) { this.actions.push("fill:" + s); this._fields[s] = v; return { payload: "filled:" + s }; }
  async waitFor(s) { this.actions.push("waitFor:" + s); return { payload: "present:" + s }; }
  async capture(k) { this.actions.push("capture:" + k); return { kind: k, payload: `capture:${k}:${this._url}` }; }
  async snapshot() { return { url: this._url, fields: { ...this._fields } }; }
}
