//! Isolated qualification bridge for a worker-owned geometry session.
use std::{cell::RefCell, io::Cursor};
use solidcraft_engine::Session;
use wasm_bindgen::prelude::*;
thread_local! {
    static SESSION: RefCell<Option<Session>> = const { RefCell::new(None) };
}
fn failure(error: impl std::fmt::Display) -> JsValue {
    JsValue::from_str(&error.to_string())
}
#[wasm_bindgen]
pub fn open(bytes: &[u8]) -> Result<(), JsValue> {
    let mut reader = solidcraft_io::DesignContainerReader::new(Cursor::new(bytes)).map_err(failure)?;
    let geometry = reader.geometry();
    let document = reader.read_document().map_err(failure)?;
    let session = Session::opened(document, geometry.as_ref());
    SESSION.with(|slot| *slot.borrow_mut() = Some(session));
    Ok(())
}
#[wasm_bindgen]
pub fn execute(command: &str, parameters: &str) -> Result<String, JsValue> {
    let parameters = serde_json::from_str(parameters).map_err(failure)?;
    SESSION.with(|slot| {
        let mut slot = slot.borrow_mut();
        let session = slot.as_mut().ok_or_else(|| failure("Document unavailable"))?;
        let result = session.execute(command, &parameters).map_err(failure)?;
        serde_json::to_string(&result).map_err(failure)
    })
}
#[wasm_bindgen]
pub fn save() -> Result<Vec<u8>, JsValue> {
    SESSION.with(|slot| {
        let slot = slot.borrow();
        let session = slot.as_ref().ok_or_else(|| failure("Document unavailable"))?;
        let saved = session.model.saved(&session.doc).ok_or_else(|| failure("Evaluated checkpoint cache unavailable"))?;
        solidcraft_io::write_design_container_with_cache(
            &session.design(), solidcraft_io::DesignCompression::Fast, None, Some(&saved),
        ).map_err(failure)
    })
}
