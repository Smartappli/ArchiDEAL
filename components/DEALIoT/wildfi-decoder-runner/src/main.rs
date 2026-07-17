use dealiot_wildfi_decoder_runner::DecoderConfig;
use std::io::Write;
use std::process::{Command, Stdio};

fn main() {
    let config = DecoderConfig::from_env();
    if let Err(error) = run(config) {
        eprintln!("{error}");
        std::process::exit(64);
    }
}

fn run(config: DecoderConfig) -> Result<(), Box<dyn std::error::Error>> {
    let stdin_script = config.stdin_script()?;
    let mut child = Command::new("java")
        .env_remove("JAVA_TOOL_OPTIONS")
        .env_remove("JDK_JAVA_OPTIONS")
        .arg(format!(
            "-Djava.io.tmpdir={}",
            std::env::var("TMPDIR").unwrap_or_else(|_| "/tmp".to_string())
        ))
        .arg("-jar")
        .arg(config.jar_path())
        .current_dir(config.workdir)
        .stdin(Stdio::piped())
        .spawn()?;

    if let Some(input) = stdin_script {
        let mut stdin = child.stdin.take().ok_or("decoder stdin unavailable")?;
        stdin.write_all(input.as_bytes())?;
    }

    let status = child.wait()?;
    if !status.success() {
        return Err(format!("WildFi decoder exited with {status}").into());
    }

    Ok(())
}
