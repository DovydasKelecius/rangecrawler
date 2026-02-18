use std::collections::HashMap;
use std::sync::Arc;

use russh::keys::ssh_key::rand_core::OsRng;
use russh::keys::{Certificate, *};
use russh::server::{Msg, Server as _, Session};
use russh::*;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio::process::Command;
use russh::CryptoVec;

#[tokio::main]
async fn main() {
    let config = russh::server::Config {
        inactivity_timeout: Some(std::time::Duration::from_secs(3600)),
        auth_rejection_time: std::time::Duration::from_secs(3),
        auth_rejection_time_initial: Some(std::time::Duration::from_secs(0)),
        keys: vec![
            russh::keys::PrivateKey::random(&mut OsRng, russh::keys::Algorithm::Ed25519).unwrap(),
        ],
        // preferred: Preferred {
        //     // kex: std::borrow::Cow::Owned(vec![russh::kex::DH_GEX_SHA256]),
        //     ..Preferred::default()
        // },
        nodelay: true,
        ..Default::default()
    };
    let config = Arc::new(config);
    let mut sh = Server {
        clients: Arc::new(Mutex::new(HashMap::new())),
        id: 0,
        buffer: String::new()
    };

    const ADDR: &str = "0.0.0.0";
    const PORT: u16 = 2222;

    match TcpListener::bind((ADDR, PORT)).await {
        Ok(socket) => {
            let server = sh.run_on_socket(config, &socket);
            let handle = server.handle();

            tokio::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(600)).await;
                handle.shutdown("Server shutting down after 10 minutes".into());
            });

            server.await.unwrap()
        }
        Err(e) => {
            eprintln!("Error: {}", e.to_string());
        }
    }

}

#[derive(Clone)]
struct Server {
    clients: Arc<Mutex<HashMap<usize, (ChannelId, russh::server::Handle)>>>,
    id: usize,
    buffer: String
}


impl server::Server for Server {
    type Handler = Self;
    fn new_client(&mut self, _: Option<std::net::SocketAddr>) -> Self {
        let s = self.clone();
        self.id += 1;
        s
    }
    fn handle_session_error(&mut self, _error: <Self::Handler as russh::server::Handler>::Error) {
        eprintln!("Session error: {_error:#?}");
    }
}

impl server::Handler for Server {
    type Error = russh::Error;

    async fn channel_open_session(
        &mut self,
        channel: Channel<Msg>,
        session: &mut Session,
    ) -> Result<bool, Self::Error> {
        {
            let mut clients = self.clients.lock().await;
            clients.insert(self.id, (channel.id(), session.handle()));
        }
        Ok(true)
    }

    async fn shell_request(
        &mut self,
        channel: ChannelId,
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        session.channel_success(channel);
        session.data(channel, CryptoVec::from(&b"rust-shell> "[..]))?;
        Ok(())
    }

    async fn auth_publickey(
        &mut self,
        _: &str,
        _key: &ssh_key::PublicKey,
    ) -> Result<server::Auth, Self::Error> {
        Ok(server::Auth::Accept)
    }

    async fn exec_request(
        &mut self,
        channel: ChannelId,
        data: &[u8], // This contains the command string
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        session.channel_success(channel); // Acknowledge the request
        let command_str = String::from_utf8_lossy(data);

        // Execute the command using sh -c
        let output = tokio::process::Command::new("sh")
            .arg("-c")
            .arg(command_str.as_ref())
            .output()
            .await;

        let response = match output {
            Ok(out) => {
                let mut combined = out.stdout;
                combined.extend(out.stderr);
                // Replace newlines with \r\n for TTY compatibility
                let text = String::from_utf8_lossy(&combined).replace("\n", "\r\n");
                CryptoVec::from(text.into_bytes())
            }
            Err(e) => CryptoVec::from(format!("Error: {}\r\n", e).into_bytes()),
        };

        session.data(channel, response)?;
        session.exit_status_request(channel, 0); // Signal that the process finished
        session.close(channel)?; 
        Ok(())
    }

    async fn pty_request(
        &mut self,
        channel: ChannelId,
        term: &str,
        col_width: u32,
        row_height: u32,
        pix_width: u32,
        pix_height: u32,
        modes: &[(Pty, u32)],
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        session.channel_success(channel);
        Ok(())
    }

    // async fn data(
    //     &mut self,
    //     channel: ChannelId,
    //     data: &[u8],
    //     session: &mut Session,
    // ) -> Result<(), Self::Error> {

    //     let response = CryptoVec::from(String::from_utf8_lossy(data));
    //     session.data(channel, response)?;

    
    //     Ok(())

    // }

    async fn data(
        &mut self,
        channel: ChannelId,
        data: &[u8],
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        for &byte in data {
            if byte == b'\r' || byte == b'\n' {
                // User pressed Enter: Execute the buffer
                let cmd = self.buffer.trim().to_string();
                self.buffer.clear();
                
                session.data(channel, CryptoVec::from(&b"\r\n"[..]))?;

                if !cmd.is_empty() {
                    let output = tokio::process::Command::new("sh").arg("-c").arg(&cmd).output().await;
                    if let Ok(out) = output {
                        let text = String::from_utf8_lossy(&out.stdout).replace("\n", "\r\n");
                        session.data(channel, CryptoVec::from(text.into_bytes()))?;
                    }
                }
                session.data(channel, CryptoVec::from(&b"rust-shell> "[..]))?;
            } else if byte == 127 { // Backspace
                self.buffer.pop();
                session.data(channel, CryptoVec::from(&b"\x08 \x08"[..]))?;
            } else {
                // Echo character and add to buffer
                self.buffer.push(byte as char);
                session.data(channel, CryptoVec::from(&[byte][..]))?;
            }
        }
        Ok(())
    }

}

impl Drop for Server {
    fn drop(&mut self) {
        let id = self.id;
        let clients = self.clients.clone();
        tokio::spawn(async move {
            let mut clients = clients.lock().await;
            clients.remove(&id);
        });
    }
}
