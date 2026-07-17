use std::env;
use std::path::PathBuf;
use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecoderConfig {
    pub decoder_home: PathBuf,
    pub workdir: PathBuf,
    pub mode: String,
    pub burst_form: String,
    pub file_index: String,
    pub tag_selection: String,
    pub imu_frequency: String,
    pub raw_input: Option<String>,
}

#[derive(Debug, Error)]
pub enum DecoderConfigError {
    #[error("Unsupported WILDFI_DECODER_MODE={0}. Use 1, 2, 3, 4, 5, 6, 7, 8 or WILDFI_DECODER_RAW_INPUT.")]
    UnsupportedMode(String),
}

impl DecoderConfig {
    pub fn from_env() -> Self {
        Self {
            decoder_home: PathBuf::from(env_or_default(
                "WILDFI_DECODER_HOME",
                "/opt/wildfi-decoder",
            )),
            workdir: PathBuf::from(env_or_default("WILDFI_DECODER_WORKDIR", "/work")),
            mode: env_or_default("WILDFI_DECODER_MODE", "2"),
            burst_form: env_or_default("WILDFI_DECODER_BURST_FORM", "0"),
            file_index: env_or_default("WILDFI_DECODER_FILE_INDEX", "0"),
            tag_selection: env_or_default("WILDFI_DECODER_TAG_SELECTION", "0"),
            imu_frequency: env_or_default("WILDFI_IMU_FREQUENCY", "25"),
            raw_input: env::var("WILDFI_DECODER_RAW_INPUT")
                .ok()
                .filter(|value| !value.is_empty()),
        }
    }

    pub fn jar_path(&self) -> PathBuf {
        self.decoder_home.join("WildFiDecoderStandalone.jar")
    }

    pub fn stdin_script(&self) -> Result<Option<String>, DecoderConfigError> {
        if let Some(raw_input) = &self.raw_input {
            return Ok(Some(unescape_raw_input(raw_input)));
        }

        match self.mode.as_str() {
            "1" | "2" => Ok(Some(format!(
                "{}\n{}\n{}\n{}\n{}\n\n99\n",
                self.mode, self.burst_form, self.file_index, self.tag_selection, self.imu_frequency
            ))),
            "3" | "4" | "5" | "6" | "7" | "8" => Ok(Some(format!("{}\n\n99\n", self.mode))),
            _ => Err(DecoderConfigError::UnsupportedMode(self.mode.clone())),
        }
    }
}

pub fn env_or_default(name: &str, default: &str) -> String {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map_or_else(|| default.to_string(), |value| value.trim().to_string())
}

fn unescape_raw_input(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch != '\\' {
            output.push(ch);
            continue;
        }
        match chars.next() {
            Some('n') => output.push('\n'),
            Some('r') => output.push('\r'),
            Some('t') => output.push('\t'),
            Some('\\') => output.push('\\'),
            Some(other) => {
                output.push('\\');
                output.push(other);
            }
            None => output.push('\\'),
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base_config(mode: &str) -> DecoderConfig {
        DecoderConfig {
            decoder_home: PathBuf::from("/opt/wildfi-decoder"),
            workdir: PathBuf::from("/work"),
            mode: mode.to_string(),
            burst_form: "0".to_string(),
            file_index: "0".to_string(),
            tag_selection: "0".to_string(),
            imu_frequency: "25".to_string(),
            raw_input: None,
        }
    }

    #[test]
    fn builds_interactive_script_for_binary_modes() {
        assert_eq!(
            base_config("2").stdin_script().unwrap().unwrap(),
            "2\n0\n0\n0\n25\n\n99\n"
        );
    }

    #[test]
    fn builds_interactive_script_for_report_modes() {
        assert_eq!(
            base_config("6").stdin_script().unwrap().unwrap(),
            "6\n\n99\n"
        );
    }

    #[test]
    fn raw_input_takes_precedence_and_unescapes_newlines() {
        let mut config = base_config("2");
        config.raw_input = Some("1\\n2\\n".to_string());

        assert_eq!(config.stdin_script().unwrap().unwrap(), "1\n2\n");
    }

    #[test]
    fn rejects_unsupported_modes() {
        assert!(matches!(
            base_config("99").stdin_script(),
            Err(DecoderConfigError::UnsupportedMode(_))
        ));
    }
}
