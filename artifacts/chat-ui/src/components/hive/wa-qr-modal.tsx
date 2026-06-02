import { Modal, Box, SpaceBetween, StatusIndicator, Spinner } from "@cloudscape-design/components";

interface WaQrModalProps {
    visible: boolean;
    qrDataUrl: string | null;
    connected: boolean;
    phone: string;
    onDismiss: () => void;
}

export function WaQrModal({ visible, qrDataUrl, connected, phone, onDismiss }: WaQrModalProps) {
    return (
        <Modal
            visible={visible}
            onDismiss={onDismiss}
            header="Link WhatsApp"
            closeAriaLabel="Close"
        >
            <SpaceBetween size="m" alignItems="center">
                {connected ? (
                    <>
                        <StatusIndicator type="success">
                            Connected to WhatsApp ({phone})
                        </StatusIndicator>
                        <p>Your WhatsApp is linked. You can close this dialog.</p>
                    </>
                ) : qrDataUrl ? (
                    <>
                        <p>Scan this QR code with your WhatsApp app:</p>
                        <p style={{ fontSize: "12px", color: "#888" }}>
                            WhatsApp → Settings → Linked Devices → Link a Device
                        </p>
                        <img
                            src={qrDataUrl}
                            alt="WhatsApp QR Code"
                            style={{ width: 280, height: 280, imageRendering: "pixelated" }}
                        />
                    </>
                ) : (
                    <>
                        <Spinner size="large" />
                        <p>Connecting to WhatsApp...</p>
                    </>
                )}
            </SpaceBetween>
        </Modal>
    );
}
