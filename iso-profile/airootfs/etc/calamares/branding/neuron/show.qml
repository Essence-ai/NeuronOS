import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 10000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1a1a2e"

            Column {
                anchors.centerIn: parent
                spacing: 30

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Welcome to NeuronOS"
                    font.pixelSize: 48
                    font.bold: true
                    color: "#4fc3f7"
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "The Linux that runs Windows apps seamlessly"
                    font.pixelSize: 24
                    color: "#ffffff"
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1a1a2e"

            Column {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "GPU Passthrough Made Easy"
                    font.pixelSize: 36
                    font.bold: true
                    color: "#4fc3f7"
                }

                Text {
                    width: 600
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "NeuronOS automatically configures VFIO GPU passthrough during installation. Run Photoshop, Premiere Pro, and games at near-native performance."
                    font.pixelSize: 18
                    color: "#ffffff"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1a1a2e"

            Column {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Seamless Windows Apps"
                    font.pixelSize: 36
                    font.bold: true
                    color: "#4fc3f7"
                }

                Text {
                    width: 600
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Windows applications appear as normal windows on your Linux desktop. No visible VM - just your apps."
                    font.pixelSize: 18
                    color: "#ffffff"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1a1a2e"

            Column {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "NeuronStore"
                    font.pixelSize: 36
                    font.bold: true
                    color: "#4fc3f7"
                }

                Text {
                    width: 600
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Install any app with one click. NeuronStore knows if an app runs natively, needs Wine, or requires a VM - and sets it up automatically."
                    font.pixelSize: 18
                    color: "#ffffff"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1a1a2e"

            Column {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Gaming Ready"
                    font.pixelSize: 36
                    font.bold: true
                    color: "#4fc3f7"
                }

                Text {
                    width: 600
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Steam with Proton for most games. GPU passthrough for anti-cheat games. Native performance, Linux freedom."
                    font.pixelSize: 18
                    color: "#ffffff"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
