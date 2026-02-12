use std::borrow::Cow;
///
/// Run this example with:
/// cargo run --example client_exec_simple -- -k <private key path> <host> <command>
///
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use russh::keys::{PrivateKeyWithHashAlg, load_openssh_certificate, load_secret_key  , ssh_key};
use russh::*;
use tokio::io::AsyncWriteExt;
use tokio::net::ToSocketAddrs;
use clap::Parser;
use std::fs;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Targets {
    group_name: String,
    end_points: Vec<String>,
    commands: Vec<String>,
}


#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
pub struct Cli {
    #[clap(long, short, default_value_t = 22)]
    port: u16,

    #[clap(long, short)]
    username: Option<String>,

    #[clap(long, short)]
    group_name: Option<String>,

    #[clap(long, short = 'o')]
    openssh_certificate: Option<PathBuf>,

    // #[clap(long, short = 'k')]
    // private_key: PathBuf,

    // #[clap(index = 1, required = true, num_args = 1.., trailing_var_arg = true, allow_hyphen_values = true)]
    // command: Vec<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    let file_path: &str = "targets.yml";
    println!("In file {file_path}");

    let contents = fs::read_to_string(file_path)?;

    let targets: Vec<Targets> = serde_yaml::from_str(contents.as_str())?;

    let private_key = "/home/andrius/.ssh/id_ed25519";
    println!("Key path: {:?}\n", private_key);

    for group in targets {
        for target in group.end_points {
            println!("Connecting to {}:{}", target, cli.port);
            println!("OpenSSH Certificate path: {:?}", cli.openssh_certificate.as_ref());
        
            // Session is a wrapper around a russh client, defined down below
            let mut ssh = Session::connect(
                private_key,
                cli.username.as_deref().unwrap_or("root"),
                None,
                (target, cli.port),
            )
            .await?;
            println!("Connected");
            
            println!("Commands to be executed: {:?}", &group.commands);
            let exit_code = ssh
                .call(
                    &group.commands
                        .join(" && "),
                )
                .await?;
        
            println!("Exitcode: {exit_code}");
            ssh.close().await?;
        }
        println!();
    }

    Ok(())
}

struct Client {}

// More SSH event handlers
// can be defined in this trait
// In this example, we're only using Channel, so these aren't needed.
impl client::Handler for Client {
    type Error = russh::Error;

    async fn check_server_key(
        &mut self,
        _server_public_key: &ssh_key::PublicKey,
    ) -> std::result::Result<bool, Self::Error> { // Explicitly use std::result
        Ok(true)
    }
}

/// This struct is a convenience wrapper
/// around a russh client
pub struct Session {
    session: client::Handle<Client>,
}

impl Session {
    async fn connect<P: AsRef<Path>, A: ToSocketAddrs>(
        key_path: P,
        user: impl Into<String>,
        openssh_cert_path: Option<P>,
        addrs: A,
    ) -> Result<Self> {
        let key_pair = load_secret_key(key_path, None)?;

        // load ssh certificate
        let mut openssh_cert = None;
        if openssh_cert_path.is_some() {
            openssh_cert = Some(load_openssh_certificate(openssh_cert_path.unwrap())?);
        }

        let config = client::Config {
            inactivity_timeout: Some(Duration::from_secs(5)),
            preferred: Preferred {
                kex: Cow::Owned(vec![
                    russh::kex::CURVE25519_PRE_RFC_8731,
                    russh::kex::EXTENSION_SUPPORT_AS_CLIENT,
                ]),
                ..Default::default()
            },
            ..<_>::default()
        };

        let config = Arc::new(config);
        let sh = Client {};

        let mut session = client::connect(config, addrs, sh).await?;
        // use publickey authentication, with or without certificate
        if openssh_cert.is_none() {
            let auth_res = session
                .authenticate_publickey(
                    user,
                    PrivateKeyWithHashAlg::new(
                        Arc::new(key_pair),
                        session.best_supported_rsa_hash().await?.flatten(),
                    ),
                )
                .await?;

            if !auth_res.success() {
                anyhow::bail!("Authentication (with publickey) failed");
            }
        } else {
            let auth_res = session
                .authenticate_openssh_cert(user, Arc::new(key_pair), openssh_cert.unwrap())
                .await?;

            if !auth_res.success() {
                anyhow::bail!("Authentication (with publickey+cert) failed");
            }
        }

        Ok(Self { session })
    }

    async fn call(&mut self, command: &str) -> Result<u32> {
        let mut channel = self.session.channel_open_session().await?;
        channel.exec(true, command).await?;

        let mut code = None;
        let mut stdout = tokio::io::stdout();

        loop {
            // There's an event available on the session channel
            let Some(msg) = channel.wait().await else {
                break;
            };
            match msg {
                // Write data to the terminal
                ChannelMsg::Data { ref data } => {
                    stdout.write_all(data).await?;
                    stdout.flush().await?;
                }
                // The command has returned an exit code
                ChannelMsg::ExitStatus { exit_status } => {
                    code = Some(exit_status);
                    // cannot leave the loop immediately, there might still be more data to receive
                }
                _ => {}
            }
        }
        Ok(code.expect("program did not exit cleanly"))
    }

    async fn close(&mut self) -> Result<()> {
        self.session
            .disconnect(Disconnect::ByApplication, "", "English")
            .await?;
        Ok(())
    }
}

