import { gql } from "@apollo/client/core";

export const GET_PROJEKTE = gql`
  query ProjektListe {
    projektList(pageSize: 100) {
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
        auftragFertig
        projektleiter
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
      auftragFertig
      projektleiter
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
