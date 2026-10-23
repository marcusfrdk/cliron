use pyo3::prelude::*;

/// The Rust internals of cliron.
#[pymodule]
mod _core {
    use pyo3::prelude::*;

    #[pymodule_init]
    fn init(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add("__version__", env!("CARGO_PKG_VERSION"))
    }
}
