import { gql } from "@apollo/client/core";

export const GET_PROJEKTE = gql`
  query ProjektListe($page: Int!) {
    projektList(
      page: $page
      pageSize: 20
      orderBy: [{ field: auftragsnummer, direction: DESC }]
    ) {
      items {
        id
        auftragsnummer
        name
        offerteSumme {
          value
          unit
        }
        wvSumme {
          value
          unit
        }
        projektPhase {
          id
          name
        }
        projektleiter { id username }
        projektKennzahlenList {
          items {
            summeWvPlus {
              value
              unit
            }
            summeIstKosten {
              value
              unit
            }
          }
        }
      }
      pageInfo {
        totalCount
      }
    }
  }
`;

export const SEARCH_PROJEKTE = gql`
  query SearchProjekte($query: String!) {
    search(query: $query, index: "projekte", types: ["Projekt"], pageSize: 20) {
      results {
        ... on ProjektType {
          id
          auftragsnummer
          name
          offerteSumme {
            value
            unit
          }
          wvSumme {
            value
            unit
          }
          projektPhase {
            id
            name
          }
          projektleiter { id username }
          projektKennzahlenList {
            items {
              summeWvPlus {
                value
                unit
              }
              summeIstKosten {
                value
                unit
              }
            }
          }
        }
      }
      total
    }
  }
`;

export const GET_PROJEKT = gql`
  query ProjektDetail($id: ID!) {
    projekt(id: $id) {
      id
      name
      auftragsnummer
      jahr
      offerteSumme {
        value
        unit
      }
      wvSumme {
        value
        unit
      }
      projektPhase {
        id
        name
      }
      projektleiter {
        id
        username
      }
      capabilities {
        canUpdate
        canDelete
      }
      projektKennzahlenList {
        items {
          summeOfferteKosten {
            value
            unit
          }
          summeWvKosten {
            value
            unit
          }
          summeIstKosten {
            value
            unit
          }
          verbrauchsrate
          deltaWvOff {
            value
            unit
          }
          deltaWvOffPct
          deltaIstPlan {
            value
            unit
          }
          deltaIstPlanPct
          summeWvPlus {
            value
            unit
          }
          bisherVerrechnet {
            value
            unit
          }
        }
      }
      kostenPositionenList {
        items {
          id
          art {
            schluessel
          }
          offerteKostenWert {
            value
            unit
          }
          offerteStunden
          wvKostenWert {
            value
            unit
          }
          wvKostenWertProzent
          offerteKostenWertProzent
        }
      }
      istWertList {
        items {
          kostenart {
            schluessel
          }
          istKostenWert {
            value
            unit
          }
          istKostenWertProzent
        }
      }
    }
  }
`;

export const GET_KOSTENART_IDS = gql`
  query KostenartIds {
    kostenartList {
      items {
        id
        schluessel
      }
    }
  }
`;

export const GET_PROJEKT_PHASE_IDS = gql`
  query ProjektPhaseIds {
    projektPhaseList {
      items {
        id
        name
      }
    }
  }
`;

export const GET_FEHLENDE_STUNDENSATZ_JAHRE = gql`
  query FehlendeStundensatzJahre {
    aufgabenStundensatz {
      fehlendeStundensatzJahre
    }
  }
`;

export const GET_STUNDENSAETZE = gql`
  query StundensaetzeListe {
    stundensatzList {
      items {
        id
        jahr
        stundensatz {
          value
          unit
        }
      }
      pageInfo {
        totalCount
      }
    }
  }
`;

export const PROJEKTLEITER = gql`
  query Projektleiter {
    benutzerList(filter: { groupsList: { any: { name: "Projektleiter" } } }) {
      items {
        id
        username
      }
    }
  }
`;

export const ME = gql`
  query Me {
    me {
      username
      capabilities {
        canCreateProjekt
        canManageStundensaetze
        canViewFinanzen
        canViewKostenPositionen
      }
    }
  }
`;

export const GET_PROJEKT_RECHNUNGEN = gql`
  query ProjektRechnungen($id: ID!) {
    projekt(id: $id) {
      id
      projektKennzahlenList {
        items {
          rechnungen {
            ...RechnungFelder
          }
        }
      }
      istWertList {
        items {
          kostenart {
            schluessel
          }
          rechnungen {
            ...RechnungFelder
          }
        }
      }
    }
  }

  fragment RechnungFelder on LieferantenrechnungType {
    id
    dokumentNr
    rechnungsdatum
    firmenname
    zeilenTitel
    status
    faelligkeitsdatum
    ueberfaellig
    betrag
    steuerBerechnet
    nettoBetrag
    buchungskonto {
      accountNo
      name
    }
  }
`;
