import { gql } from "@apollo/client/core";

export const CREATE_PROJEKT = gql`
  mutation CreateProjekt(
    $name: String!
    $auftragsnummer: String!
    $jahr: Int!
    $offerteSumme: MeasurementScalar!
    $wvSumme: MeasurementScalar
    $projektleiter: String
  ) {
    createProjekt(
      name: $name
      auftragsnummer: $auftragsnummer
      jahr: $jahr
      offerteSumme: $offerteSumme
      wvSumme: $wvSumme
      projektleiter: $projektleiter
    ) {
      success
      Projekt {
        id
      }
    }
  }
`;

export const UPDATE_PROJEKT = gql`
  mutation UpdateProjekt(
    $id: Int!
    $name: String
    $offerteSumme: MeasurementScalar
    $wvSumme: MeasurementScalar
    $projektleiter: String
    $auftragFertig: Boolean
  ) {
    updateProjekt(
      id: $id
      name: $name
      offerteSumme: $offerteSumme
      wvSumme: $wvSumme
      projektleiter: $projektleiter
      auftragFertig: $auftragFertig
    ) {
      success
    }
  }
`;

export const UPDATE_KOSTEN_POSITION = gql`
  mutation UpdateKostenPosition($id: Int!, $offerteKostenWert: MeasurementScalar) {
    updateKostenPosition(id: $id, offerteKostenWert: $offerteKostenWert) {
      success
    }
  }
`;

export const CREATE_KOSTEN_POSITION = gql`
  mutation CreateKostenPosition(
    $projekt: ID!
    $art: ID!
    $offerteKostenWert: MeasurementScalar
  ) {
    createKostenPosition(projekt: $projekt, art: $art, offerteKostenWert: $offerteKostenWert) {
      success
    }
  }
`;

export const DELETE_KOSTEN_POSITION = gql`
  mutation DeleteKostenPosition($id: Int!) {
    deleteKostenPosition(id: $id) {
      success
    }
  }
`;

export const CREATE_STUNDENSATZ = gql`
  mutation CreateStundensatz($jahr: Int!, $stundensatz: MeasurementScalar!) {
    createStundensatz(jahr: $jahr, stundensatz: $stundensatz) {
      success
      Stundensatz {
        id
      }
    }
  }
`;

export const UPDATE_STUNDENSATZ = gql`
  mutation UpdateStundensatz($id: Int!, $stundensatz: MeasurementScalar!) {
    updateStundensatz(id: $id, stundensatz: $stundensatz) {
      success
    }
  }
`;

export const DELETE_STUNDENSATZ = gql`
  mutation DeleteStundensatz($id: Int!) {
    deleteStundensatz(id: $id) {
      success
    }
  }
`;
